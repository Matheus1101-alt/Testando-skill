#!/usr/bin/env python3
"""Montagem sincronizada: clipes gerados por IA + narração + trilha → MP4.

Subcomandos (rode na ordem):
  analisar  --clipes A.mp4 B.mp4 … --narracao N.wav [--trilha T.mp3] --saida DIR
            Mede clipes e áudio, detecta o "flash" da imagem de referência, gera folha de
            contato e grades 1 quadro/s com o número REAL do quadro, e cria DIR/plano.json.
  alinhar   DIR/plano.json --texto transcricao.txt
            Divide o texto em frases e encontra o início de cada uma pelas pausas da narração.
  plano     DIR/plano.json
            Valida o plano de corte e imprime o mapa (velocidades, congelamentos, avisos).
  remendo   DIR/plano.json --clipe Cxx [--quadro N]
            Prévia dos remendos de um clipe: antes/depois, brilho da origem × entorno, sobreposição e
            quadro a quadro na entrada/saída do remendo (desde/ate).
  render    DIR/plano.json [--saida DIR_ENTREGA] [--trabalho DIR]
            Renderiza vídeo + áudio, mede e gera folha de revisão, medicoes.json e mapa_de_corte.md;
            copia este script e um plano.json com caminhos absolutos para a entrega.

Requer ffmpeg/ffprobe ≥ 5 (libx264, libsoxr) e Python 3.9+. Sem dependências Python externas.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
import unicodedata
from collections import Counter
from fractions import Fraction
from pathlib import Path

# Valores padrão — o plano.json pode sobrescrever qualquer um (chaves "video" e "audio").
VIDEO_PADRAO = {
    "fps": None,                 # None = fps mais comum entre os clipes
    "largura": None,             # None = menor resolução entre os clipes (nunca aumenta)
    "altura": None,
    "ajuste": "crop",            # clipe com proporção diferente: "crop" (preenche) ou "pad" (barras)
    "abertura_s": 1.5,           # quadro parado antes da narração
    "fade_in_s": 1.0,
    "final_s": 3.5,              # duração depois da última palavra
    "fade_out_s": 2.5,
    "antecipar_quadros": 2,      # o corte cai N quadros antes do início da frase
    "vel_min": 0.67,             # abaixo disso congela o último quadro
    "vel_max": 1.33,
    "aviso_congelamento_s": 3.0,
    "aviso_trecho_min_s": 2.5,
    "aviso_congelamento_total_pct": 8.0,   # soma dos congelamentos (sem a abertura) em % do vídeo
    "crf": 18,
}
AUDIO_PADRAO = {
    "trilha_inicio_s": 0.0,
    "musica_abaixo_da_voz_db": 12.0,   # voz − música na janela de fala, já com ducking
    "ducking_limiar": 0.02, "ducking_ratio": 8, "ducking_ataque_ms": 40, "ducking_release_ms": 600,
    "segurar_pausas_s": 1.2,           # 0 = chave literal (a narração); >0 = envelope fala/pausa
    "ducking_antecipar_s": 0.1,
    "ducking_profundidade_db": 8.0,    # só vale com segurar_pausas_s > 0
    "silencio_db": -35, "silencio_min_s": 0.15,
    "alvo_lufs": -14.0, "alvo_tp": -1.5,
    "teto_limitador_db": -2.3,
    "aac": "192k", "taxa": 48000,
}


# ------------------------------------------------------------------ utilitários

def run(cmd: list[str], capture: bool = False, quiet: bool = True) -> str:
    if not quiet:
        print("  $", " ".join(cmd[:8]), "…" if len(cmd) > 8 else "")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stderr[-4000:])
        raise SystemExit(f"falhou: {' '.join(cmd[:12])}")
    return res.stderr if capture else res.stdout


def probe(path: Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    return json.loads(out)


def video_info(path: Path) -> dict:
    p = probe(path)
    v = next(s for s in p["streams"] if s["codec_type"] == "video")
    fps = Fraction(v.get("avg_frame_rate") or v["r_frame_rate"])
    if fps == 0:
        fps = Fraction(v["r_frame_rate"])
    frames = int(v["nb_frames"]) if v.get("nb_frames", "").isdigit() else None
    if frames is None:
        frames = int(run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_frames", "-of", "csv=p=0", str(path)]).strip())
    return {"largura": int(v["width"]), "altura": int(v["height"]), "fps": float(fps), "fps_frac": str(fps),
            "quadros": frames, "duracao_s": float(p["format"]["duration"]), "codec": v["codec_name"],
            "tem_audio": any(s["codec_type"] == "audio" for s in p["streams"]),
            "encoder": p["format"].get("tags", {}).get("encoder", "")}


def audio_info(path: Path) -> dict:
    p = probe(path)
    a = next(s for s in p["streams"] if s["codec_type"] == "audio")
    return {"codec": a["codec_name"], "taxa": int(a["sample_rate"]), "canais": int(a["channels"]),
            "duracao_s": float(p["format"]["duration"])}


def loudness(path: Path, start: float | None = None, dur: float | None = None, pre: str = "") -> dict:
    cmd = ["ffmpeg", "-hide_banner", "-nostats"]
    if start is not None:
        cmd += ["-ss", f"{start}"]
    if dur is not None:
        cmd += ["-t", f"{dur}"]
    cmd += ["-i", str(path), "-af", f"{pre}ebur128=peak=true", "-f", "null", "-"]
    err = run(cmd, capture=True)
    s = err[err.rfind("Summary:"):]
    num = lambda pat: float(re.search(pat, s).group(1).replace("-inf", "-120"))
    return {"I": num(r"I:\s+(-?[\d.]+|-inf) LUFS"), "TP": num(r"Peak:\s+(-?[\d.]+|-inf) dBFS"),
            "LRA": num(r"LRA:\s+(-?[\d.]+) LU")}


def per_frame_metric(path: Path, vf: str, key: str = "lavfi.signalstats.YAVG") -> list[float]:
    out = run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"{vf},metadata=print:key={key}:file=-",
               "-f", "null", "-"])
    return [float(x) for x in re.findall(re.escape(key) + r"=(-?[\d.]+)", out)]


def silences(path: Path, db: float, min_s: float) -> list[tuple[float, float]]:
    err = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
               f"silencedetect=noise={db}dB:d={min_s}", "-f", "null", "-"], capture=True)
    st = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    dur = audio_info(path)["duracao_s"]
    en += [dur] * (len(st) - len(en))
    return [(max(0.0, a), b) for a, b in zip(st, en)]


def count_frames(path: Path) -> int:
    return int(run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                    "stream=nb_read_frames", "-of", "csv=p=0", str(path)]).strip())


def resolve(base: Path, p: str | None) -> Path | None:
    if not p:
        return None
    q = Path(p)
    return q if q.is_absolute() else (base / q).resolve()


def fmt(t: float) -> str:
    return f"{t:.2f}".replace(".", ",")


# ------------------------------------------------------------------ analisar

def analyze_clip(cid: str, path: Path, out: Path) -> dict:
    info = video_info(path)
    fps = info["fps"]
    # movimento por 0,5 s (diferença entre quadros)
    motion = per_frame_metric(path, "scale=320:-2,format=gray,tblend=all_mode=difference,signalstats")
    step = max(1, round(fps / 2))
    buckets = [round(sum(motion[i:i + step]) / len(motion[i:i + step]), 1) for i in range(0, len(motion), step)]
    moving = [i for i, b in enumerate(buckets) if b > 1.0]
    settle = (moving[-1] + 1) * 0.5 if moving else 0.0  # fim do último meio segundo com movimento
    # flash da imagem de referência: começo "cheio" que some para um quadro quase vazio
    first = int(fps * 1.5)
    edges = per_frame_metric(path, f"select='lt(n,{first})',scale=320:-2,edgedetect=low=0.1:high=0.3,signalstats")
    last_edges = per_frame_metric(path, f"select='gte(n,{info['quadros'] - 2})',scale=320:-2,"
                                        "edgedetect=low=0.1:high=0.3,signalstats")
    e_last = last_edges[-1] if last_edges else 0
    flash, safe = False, 0
    if edges and edges[0] >= 0.6 * max(e_last, 1e-6):
        m = min(edges)
        if m <= 0.5 * edges[0]:
            flash = True
            safe = next(i for i, e in enumerate(edges) if e <= m + 0.05 * (edges[0] - m))
    # imagens: grade 1 quadro/s com o número do quadro de ORIGEM (drawtext antes do select)
    lbl = f"drawtext=text='{cid} q%{{n}} %{{pts\\:hms}}':x=6:y=6:fontsize=20:fontcolor=white:box=1:boxcolor=black@0.6"
    cols = 4
    rows = math.ceil(math.ceil(info["duracao_s"]) / cols)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vf",
         f"scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2,{lbl},"
         f"select='not(mod(n,{round(fps)}))',tile={cols}x{rows}",
         "-frames:v", "1", "-q:v", "3", str(out / f"grade_{cid}.jpg")])
    return {"id": cid, "arquivo": str(path), **info, "movimento_0_5s": buckets, "assenta_em_s": settle,
            "flash_inicial": flash, "inicio_seguro_quadro": safe}


def contact_sheet(clips: list[dict], out: Path) -> None:
    tiles = []
    for c in clips:
        for k, frac in enumerate((0.03, 0.5, 0.99)):
            n = min(c["quadros"] - 1, max(c["inicio_seguro_quadro"], int(c["quadros"] * frac)))
            png = out / f"_cs_{c['id']}_{k}.png"
            run(["ffmpeg", "-v", "error", "-y", "-i", c["arquivo"], "-vf",
                 f"select='eq(n,{n})',scale=480:270:force_original_aspect_ratio=decrease,"
                 f"pad=480:270:(ow-iw)/2:(oh-ih)/2,drawtext=text='{c['id']} q{n}':x=8:y=8:fontsize=22:"
                 "fontcolor=white:box=1:boxcolor=black@0.6", "-frames:v", "1", str(png)])
            tiles.append(png)
    args = sum((["-i", str(t)] for t in tiles), [])
    layout = "|".join(f"{c * 480}_{r * 270}" for r in range(len(clips)) for c in range(3))
    run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex",
         f"{''.join(f'[{i}:v]' for i in range(len(tiles)))}xstack=inputs={len(tiles)}:layout={layout}:fill=black[o]",
         "-map", "[o]", "-q:v", "3", str(out / "folha_de_contato.jpg")])
    for t in tiles:
        t.unlink()


def music_profile(path: Path) -> dict:
    out = run(["ffmpeg", "-v", "error", "-i", str(path), "-af",
               "ebur128=metadata=1,ametadata=print:key=lavfi.r128.S:file=-", "-f", "null", "-"])
    per_s: dict[int, float] = {}
    t = 0.0
    for line in out.splitlines():
        if m := re.search(r"pts_time:([\d.]+)", line):
            t = float(m.group(1))
        elif m := re.search(r"lavfi.r128.S=(-?[\d.]+|-inf)", line):
            per_s.setdefault(int(t), -120.0 if m.group(1) == "-inf" else float(m.group(1)))
    L = loudness(path)
    seq = [per_s[k] for k in sorted(per_s)]
    lead = next((i for i, v in enumerate(seq) if v > -50), 0)
    body = next((i for i in range(len(seq)) if all(v >= L["I"] - 4 for v in seq[i:i + 10])), lead)
    return {**audio_info(path), **L, "curto_prazo_por_s": [round(v, 1) for v in seq],
            "silencio_inicial_s": lead, "inicio_sugerido_s": body}


def cmd_analisar(a: argparse.Namespace) -> None:
    out = Path(a.saida).resolve()
    out.mkdir(parents=True, exist_ok=True)
    paths = [Path(p).resolve() for p in a.clipes]
    if a.ordenar == "horario":  # último bloco de ≥8 dígitos no nome (ex.: ..._20261003151242.mp4)
        def stamp(p: Path) -> str:
            runs = re.findall(r"\d{8,}", p.stem)
            return runs[-1] if runs else p.stem
        paths.sort(key=stamp)
    elif a.ordenar == "nome":
        paths.sort(key=lambda p: p.name)
    clips = []
    for i, p in enumerate(paths, 1):
        cid = f"C{i:02d}"
        print(f"  analisando {cid}: {p.name}")
        clips.append(analyze_clip(cid, p, out))
    contact_sheet(clips, out)

    narr = Path(a.narracao).resolve()
    sil = silences(narr, AUDIO_PADRAO["silencio_db"], AUDIO_PADRAO["silencio_min_s"])
    narr_info = {**audio_info(narr), **loudness(narr),
                 "I_estereo": loudness(narr, pre="pan=stereo|c0=c0|c1=c0,")["I"],
                 "silencios": [[round(x, 3), round(y, 3)] for x, y in sil]}
    music = music_profile(Path(a.trilha).resolve()) if a.trilha else None

    res = Counter((c["largura"], c["altura"]) for c in clips)
    fpss = Counter(round(c["fps"], 3) for c in clips)
    smallest = min(res, key=lambda r: r[0] * r[1])
    analise = {"clipes": clips, "narracao": narr_info, "trilha": music,
               "resolucoes": {f"{w}x{h}": n for (w, h), n in res.items()},
               "fps": {str(k): n for k, n in fpss.items()}}
    (out / "analise.json").write_text(json.dumps(analise, indent=1, ensure_ascii=False))

    plano_path = out / "plano.json"
    if not plano_path.exists():
        plano = {
            "nome": a.nome or "video_final",
            "analise": "analise.json",
            "arquivos": {"clipes": {c["id"]: c["arquivo"] for c in clips}, "narracao": str(narr),
                         "trilha": str(Path(a.trilha).resolve()) if a.trilha else None},
            "video": {}, "audio": {"trilha_inicio_s": music["inicio_sugerido_s"] if music else 0},
            "frases": [], "fim_ultima_palavra": None, "cortes": [], "remendos": {},
        }
        plano_path.write_text(json.dumps(plano, indent=1, ensure_ascii=False))

    total = sum(c["duracao_s"] for c in clips)
    print("\nCLIPES")
    print(" id   resolução   fps     dur(s)  quadros  áudio  flash→início seguro  assenta(s)  arquivo")
    for c in clips:
        fl = f"sim → q{c['inicio_seguro_quadro']}" if c["flash_inicial"] else "não"
        print(f" {c['id']}  {c['largura']}x{c['altura']}  {c['fps']:6.3f}  {c['duracao_s']:6.2f}  {c['quadros']:6d}"
              f"   {'sim' if c['tem_audio'] else 'não':3}   {fl:20} {c['assenta_em_s']:5.1f}     {Path(c['arquivo']).name}")
    print(f"\n soma dos clipes: {total:.2f} s | narração: {narr_info['duracao_s']:.2f} s")
    if any(c["tem_audio"] for c in clips):
        print(" • o áudio próprio dos clipes é descartado na montagem (só narração + trilha)")
    if len(res) > 1 or len(fpss) > 1:
        print(f" ⚠ resoluções/fps misturados: {dict(analise['resolucoes'])} {dict(analise['fps'])} — "
              f"alvo sem aumentar resolução: {smallest[0]}x{smallest[1]}")
    print(f"\nNARRAÇÃO  {narr_info['canais']} canal(is) {narr_info['taxa']} Hz | {narr_info['I']:.1f} LUFS "
          f"({narr_info['I_estereo']:.1f} em estéreo) | pico {narr_info['TP']:.1f} dBTP | {len(sil)} pausas ≥ "
          f"{AUDIO_PADRAO['silencio_min_s']} s")
    if music:
        print(f"TRILHA    {music['duracao_s']:.1f} s | {music['I']:.1f} LUFS | pico {music['TP']:.1f} dBTP"
              f"{' ⚠ clipada na origem' if music['TP'] > -0.1 else ''} | silêncio inicial {music['silencio_inicial_s']} s"
              f" | ganha corpo em ~{music['inicio_sugerido_s']} s")
    print(f"\nok: {out/'analise.json'} | {out/'plano.json'} | folha_de_contato.jpg | grade_Cxx.jpg")


# ------------------------------------------------------------------ alinhar

def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    parts = re.split(r"(?<=[.!?…])\s+(?=[^\s])", text)
    return [p.strip() for p in parts if p.strip()]


def syllables(s: str) -> float:
    """Estimativa de sílabas (pt/es/en): grupos de vogais + números e siglas aproximados."""
    total = 0.0
    for tok in re.findall(r"\w+", s):
        if tok.isdigit():
            total += {1: 2, 2: 3.5, 3: 6, 4: 11}.get(len(tok), 3 * len(tok))
        elif tok.isupper() and len(tok) > 1:
            total += 1.3 * len(tok)
        else:
            plain = unicodedata.normalize("NFD", tok.lower())
            plain = "".join(ch for ch in plain if unicodedata.category(ch) != "Mn")
            total += max(1, len(re.findall(r"[aeiouy]+", plain)))
    return total


def align(sentences: list[str], sil: list[tuple[float, float]], dur: float) -> list[dict]:
    """Escolhe N−1 pausas como fronteiras de frase (programação dinâmica): minimiza a variação
    da velocidade de fala entre frases e favorece pausas mais longas."""
    lead = sil[0][1] if sil and sil[0][0] <= 0.05 else 0.0
    tail = sil[-1][0] if sil and sil[-1][1] >= dur - 0.05 else dur
    inner = [(a, b) for a, b in sil if a > lead + 0.05 and b < tail - 0.05]
    n, m = len(sentences), len(inner)
    syl = [syllables(s) for s in sentences]
    if n == 1:
        return [{"n": 1, "inicio": round(lead, 3), "fim": round(tail, 3), "texto": sentences[0]}]
    if m < n - 1:
        raise SystemExit(f"há {n} frases mas só {m} pausas — revise o texto ou reduza silencio_min_s")
    speech = (tail - lead) - sum(b - a for a, b in inner if b - a >= 0.4)
    rate = sum(syl) / max(speech, 1e-6)

    def cost(k: int, start: float, end: float) -> float:
        d = max(end - start, 0.05)
        return math.log((syl[k] / d) / rate) ** 2

    INF = float("inf")
    # dp[k][j]: melhor custo com a frase k terminando na pausa j (fronteira j)
    dp = [[INF] * m for _ in range(n - 1)]
    back = [[-1] * m for _ in range(n - 1)]
    for j in range(m):
        dp[0][j] = cost(0, lead, inner[j][0]) - 0.6 * min(inner[j][1] - inner[j][0], 1.0)
    for k in range(1, n - 1):
        for j in range(k, m):
            best, arg = INF, -1
            for i in range(k - 1, j):
                if dp[k - 1][i] < INF:
                    c = dp[k - 1][i] + cost(k, inner[i][1], inner[j][0])
                    if c < best:
                        best, arg = c, i
            if arg >= 0:
                dp[k][j] = best - 0.6 * min(inner[j][1] - inner[j][0], 1.0)
                back[k][j] = arg
    best, j = min((dp[n - 2][j] + cost(n - 1, inner[j][1], tail), j) for j in range(n - 2, m))
    picks = [j]
    for k in range(n - 2, 0, -1):
        j = back[k][j]
        picks.append(j)
    picks.reverse()
    bounds = [lead] + [inner[j][1] for j in picks]
    ends = [inner[j][0] for j in picks] + [tail]
    out = []
    for k, s in enumerate(sentences):
        d = ends[k] - bounds[k]
        out.append({"n": k + 1, "inicio": round(bounds[k], 3), "fim": round(ends[k], 3), "texto": s,
                    "silabas_s": round(syl[k] / d, 1),
                    "pausa_antes_s": round(inner[picks[k - 1]][1] - inner[picks[k - 1]][0], 2) if k else None})
    return out


def cmd_alinhar(a: argparse.Namespace) -> None:
    pp = Path(a.plano).resolve()
    plano = json.loads(pp.read_text())
    base = pp.parent
    narr = resolve(base, plano["arquivos"]["narracao"])
    au = {**AUDIO_PADRAO, **plano.get("audio", {})}
    sents = split_sentences(Path(a.texto).read_text(encoding="utf-8"))
    frases = align(sents, silences(narr, au["silencio_db"], au["silencio_min_s"]), audio_info(narr)["duracao_s"])
    plano["frases"] = [{"n": f["n"], "inicio": f["inicio"], "texto": f["texto"]} for f in frases]
    plano["fim_ultima_palavra"] = frases[-1]["fim"]
    pp.write_text(json.dumps(plano, indent=1, ensure_ascii=False))
    rates = [f["silabas_s"] for f in frases]
    med = statistics.median(rates)
    print(f"\n {'#':>2}  início   fim     síl/s  pausa  frase")
    for f in frases:
        flag = " ⚠ confira" if abs(f["silabas_s"] / med - 1) > 0.3 else ""
        pa = f"{f['pausa_antes_s']:.2f}" if f["pausa_antes_s"] is not None else "  — "
        print(f" {f['n']:2d}  {f['inicio']:6.2f}  {f['fim']:6.2f}  {f['silabas_s']:5.1f}  {pa}  {f['texto'][:70]}{flag}")
    print(f"\n velocidade mediana {med:.1f} síl/s | última palavra termina em {frases[-1]['fim']:.2f} s"
          f"\n ok: frases gravadas em {pp}")


# ------------------------------------------------------------------ plano / linha do tempo

def load_plan(path: Path) -> tuple[dict, Path, dict, dict, dict]:
    plano = json.loads(path.read_text())
    base = path.parent
    an_path = resolve(base, plano.get("analise"))
    an = json.loads(an_path.read_text()) if an_path and an_path.exists() else None
    if an is None:
        print(" ⚠ analise.json não encontrado — avisos de flash inicial DESATIVADOS (confira 'analise' no plano)")
    vid = {**VIDEO_PADRAO, **plano.get("video", {})}
    aud = {**AUDIO_PADRAO, **plano.get("audio", {})}
    clips = {cid: video_info(resolve(base, p)) | {"arquivo": str(resolve(base, p))}
             for cid, p in plano["arquivos"]["clipes"].items()}
    if not vid["fps"]:
        vid["fps"] = Counter(round(c["fps"], 3) for c in clips.values()).most_common(1)[0][0]
    if not vid["largura"]:
        w, h = min(((c["largura"], c["altura"]) for c in clips.values()), key=lambda r: r[0] * r[1])
        vid["largura"], vid["altura"] = w, h
    return plano, base, vid, aud, {"clipes": clips, "analise": an}


def timeline(plano: dict, vid: dict, ctx: dict) -> tuple[list[dict], int]:
    fps = vid["fps"]
    starts = {f["n"]: f["inicio"] for f in plano["frases"]}
    total = round((vid["abertura_s"] + plano["fim_ultima_palavra"] + vid["final_s"]) * fps)
    intro = round(vid["abertura_s"] * fps)
    cuts = [0 if i == 0 else round((vid["abertura_s"] + starts[c["frase"]]) * fps) - vid["antecipar_quadros"]
            for i, c in enumerate(plano["cortes"])] + [total]
    flashes = {c["id"]: c for c in (ctx["analise"] or {}).get("clipes", [])}
    usage = Counter(c["clipe"] for c in plano["cortes"])
    segs = []
    for i, c in enumerate(plano["cortes"]):
        info = ctx["clipes"][c["clipe"]]
        n = cuts[i + 1] - cuts[i]
        hold = intro if i == 0 else 0
        src_s = (c["ate"] - c["de"] + 1) / info["fps"]
        play_s = (n - hold) / fps
        speed, freeze, warns = src_s / play_s, 0, []
        if speed < vid["vel_min"]:
            speed = vid["vel_min"]
            freeze = (n - hold) - math.floor(src_s / speed * fps)
        if speed > vid["vel_max"] + 1e-9:
            warns.append(f"velocidade {speed:.2f}x acima de {vid['vel_max']}x — encurte o trecho do clipe")
        if freeze / fps > vid["aviso_congelamento_s"]:
            warns.append(f"congelamento de {freeze / fps:.1f} s — gerar clipe mais longo")
        if n / fps < vid["aviso_trecho_min_s"]:
            warns.append(f"trecho de {n / fps:.1f} s — curto demais (junte com a frase vizinha ou gere clipe)")
        fl = flashes.get(c["clipe"])
        if fl and fl["flash_inicial"] and c["de"] < fl["inicio_seguro_quadro"]:
            warns.append(f"começa no quadro {c['de']}, dentro do flash da imagem de referência "
                         f"(início seguro: q{fl['inicio_seguro_quadro']})")
        if c["ate"] >= info["quadros"]:
            warns.append(f"quadro final {c['ate']} além do fim do clipe ({info['quadros'] - 1})")
        if usage[c["clipe"]] > 1:
            warns.append(f"{c['clipe']} usado {usage[c['clipe']]}x no vídeo (repetição)")
        if i == 0 and c["frase"] != min(starts):
            warns.append(f"o primeiro corte cobre desde o início do vídeo; 'frase' {c['frase']} é ignorada — use {min(starts)}")
        nxt = plano["cortes"][i + 1]["frase"] if i + 1 < len(plano["cortes"]) else max(starts) + 1
        segs.append({"idx": i + 1, "frases": list(range(c["frase"], nxt)), "clipe": c["clipe"], "de": c["de"],
                     "ate": c["ate"], "inicio": cuts[i], "n": n, "hold": hold, "vel": speed, "congela": freeze,
                     "nota": c.get("nota", ""), "avisos": warns, "fps_src": info["fps"]})
    return segs, total


def map_table(segs: list[dict], fps: float, plano: dict) -> str:
    texts = {f["n"]: f["texto"] for f in plano["frases"]}
    rows = ["| # | Tempo (s) | Narração | Clipe (quadros) | Velocidade | Congelamento |", "|---|---|---|---|---|---|"]
    for s in segs:
        t0, t1 = s["inicio"] / fps, (s["inicio"] + s["n"]) / fps
        narr = " / ".join(f"{k}. {texts.get(k, '')[:60]}" for k in s["frases"])
        frz = (f"{s['hold'] / fps:.1f} s abertura" if s["hold"] else "") + \
              (f"{' + ' if s['hold'] else ''}{s['congela'] / fps:.2f} s" if s["congela"] else "")
        rows.append(f"| {s['idx']} | {fmt(t0)}–{fmt(t1)} | {narr} | {s['clipe']} ({s['de']}–{s['ate']}) "
                    f"| {s['vel']:.2f}x | {frz or '—'} |")
    return "\n".join(rows)


def cmd_plano(a: argparse.Namespace) -> None:
    plano, base, vid, aud, ctx = load_plan(Path(a.plano).resolve())
    if not plano["frases"] or not plano["cortes"]:
        raise SystemExit("plano sem frases ou sem cortes — rode 'alinhar' e preencha 'cortes'")
    segs, total = timeline(plano, vid, ctx)
    print(map_table(segs, vid["fps"], plano))
    print(f"\n saída: {vid['largura']}x{vid['altura']} @ {vid['fps']} fps | {total} quadros = {total / vid['fps']:.3f} s")
    n_warn = 0
    for s in segs:
        for w in s["avisos"]:
            print(f" ⚠ trecho {s['idx']} ({s['clipe']}): {w}")
            n_warn += 1
    frozen = sum(s["congela"] for s in segs) / vid["fps"]
    pct = 100 * frozen / (total / vid["fps"])
    slow = [s["idx"] for s in segs if s["vel"] <= 0.70 + 1e-9]
    if pct > vid["aviso_congelamento_total_pct"]:
        print(f" ⚠ congelamento somado {frozen:.1f} s = {pct:.0f}% do vídeo (limite {vid['aviso_congelamento_total_pct']:.0f}%)"
              " — prefira cortar o trecho ou mostre a troca ao usuário")
        n_warn += 1
    multi = [s for s in segs if len(s["frases"]) > 1]
    for s in multi:
        print(f" • trecho {s['idx']} cobre as frases {s['frases']} com um só clipe — confira se todas têm imagem")
    print(f" • congelado no total: {frozen:.1f} s ({pct:.0f}%, sem a abertura) | trechos a ≤0,70x: {slow or 'nenhum'}")
    print(f" • quadro parado da abertura = quadro {segs[0]['de']} de {segs[0]['clipe']}")
    print(f"\n {n_warn} aviso(s)")


# ------------------------------------------------------------------ render: vídeo

def patch_graph(patches: list[dict], first_frame: int, label: str = "v0") -> tuple[str, str]:
    """Remendos: copia um retângulo (sx, sy) do mesmo quadro sobre (x, y), com borda suave.
    first_frame = quadro de origem do primeiro quadro do trecho (para desde/ate)."""
    g = ""
    for j, p in enumerate(patches):
        dist = "min(min(X,W-1-X),Y)" if p.get("borda_inferior") is False else "min(min(X,W-1-X),min(Y,H-1-Y))"
        start = p.get("desde", 0) - first_frame
        cond = [f"gte(n,{start})"] if start > 0 else []
        if p.get("ate") is not None:
            cond.append(f"lte(n,{p['ate'] - first_frame})")
        enable = f":enable='{'*'.join(cond)}'" if cond else ""
        g += (f";[{label}]split[b{j}][s{j}];[s{j}]crop={p['w']}:{p['h']}:{p['sx']}:{p['sy']},format=rgba,"
              f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='255*clip({dist}/{p.get('borda', 5)},0,1)'[p{j}];"
              f"[b{j}][p{j}]overlay={p['x']}:{p['y']}{enable}[{label}p{j}]")
        label = f"{label}p{j}"
    return g, label


def render_segment(s: dict, clip: dict, vid: dict, patches: list[dict], out: Path) -> None:
    fps, W, H = vid["fps"], vid["largura"], vid["altura"]
    g = f"[0:v]trim=start_frame={s['de']}:end_frame={s['ate'] + 1},setpts=PTS-STARTPTS[v0]"
    pg, label = patch_graph(patches, s["de"])
    g += pg
    fit = ""
    if (clip["largura"], clip["altura"]) != (W, H):
        fit = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}," if vid["ajuste"] == "crop" else
               f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,")
    pad = f"tpad=stop_mode=clone:stop={s['n']}"
    if s["hold"]:
        pad = f"tpad=start_mode=clone:start={s['hold']}:stop_mode=clone:stop={s['n']}"
    # setpts + fps: duplica/descarta quadros inteiros, sem interpolação
    g += (f";[{label}]{fit}setpts=PTS/{s['vel']:.6f},fps={fps},{pad},trim=end_frame={s['n']},"
          f"setpts=PTS-STARTPTS,setsar=1,format=yuv420p[out]")
    run(["ffmpeg", "-v", "error", "-y", "-i", clip["arquivo"], "-filter_complex", g, "-map", "[out]", "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-qp", "0", str(out)])
    got = count_frames(out)
    if got != s["n"]:
        raise SystemExit(f"trecho {s['idx']}: {got} quadros, esperado {s['n']}")


def build_video(plano: dict, vid: dict, ctx: dict, segs: list[dict], total: int, work: Path) -> Path:
    parts = []
    for s in segs:
        out = work / f"seg{s['idx']:02d}_{s['clipe']}.mp4"
        print(f"  trecho {s['idx']:2d}  {s['clipe']}  {s['vel']:.3f}x")
        render_segment(s, ctx["clipes"][s["clipe"]], vid, plano.get("remendos", {}).get(s["clipe"], []), out)
        parts.append(out)
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    joined = work / "video_concat.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
    if count_frames(joined) != total:
        raise SystemExit("contagem de quadros da junção não bate")
    return joined


def yavg(path: Path, frame: int, x: int, y: int, w: int, h: int) -> float | None:
    if w <= 0 or h <= 0:
        return None
    vals = per_frame_metric(path, f"select='eq(n,{frame})',crop={w}:{h}:{x}:{y},signalstats")
    return vals[0] if vals else None


def cmd_remendo(a: argparse.Namespace) -> None:
    plano, base, vid, aud, ctx = load_plan(Path(a.plano).resolve())
    cid = a.clipe
    patches = plano.get("remendos", {}).get(cid, [])
    if not patches:
        raise SystemExit(f"nenhum remendo definido para {cid}")
    clip = ctx["clipes"][cid]
    src = Path(clip["arquivo"])
    W, H, last = clip["largura"], clip["altura"], clip["quadros"] - 1
    q = a.quadro if a.quadro is not None else last - 1
    out = Path(a.saida).resolve() if a.saida else Path(a.plano).resolve().parent
    out.mkdir(parents=True, exist_ok=True)

    def patched_frames(first: int, count: int, path: Path, crop: str, cols: int) -> None:
        g = f"[0:v]trim=start_frame={first}:end_frame={first + count},setpts=PTS-STARTPTS[v0]"
        pg, lab = patch_graph(patches, first)
        g += pg + (f";[{lab}]{crop},drawtext=text='q%{{eif\\:n+{first}\\:d}}':x=4:y=4:fontsize=18:fontcolor=white:"
                   f"box=1:boxcolor=black@0.6,tile={cols}x{math.ceil(count / cols)}[o]")
        run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", g, "-map", "[o]", "-frames:v", "1",
             "-q:v", "2", str(path)])

    print(f"remendos de {cid} (quadro de referência q{q})")
    for i, p in enumerate(patches):
        x, y, w, h, sx, sy, bd = p["x"], p["y"], p["w"], p["h"], p["sx"], p["sy"], p.get("borda", 5)
        # 1) brilho: origem × anel de 6 px em volta do destino
        ring = [r for r in (yavg(src, q, x, max(0, y - 6), w, min(6, y)),
                            yavg(src, q, x, y + h, w, min(6, H - y - h)),
                            yavg(src, q, max(0, x - 6), y, min(6, x), h),
                            yavg(src, q, x + w, y, min(6, W - x - w), h)) if r is not None]
        ys = yavg(src, q, sx, sy, w, h)
        diff = ys - statistics.mean(ring) if ring else 0.0
        flag = "  ⚠ acima de 4 níveis a costura tende a aparecer: escolha outra origem ou divida o remendo" \
            if abs(diff) > 4 else ""
        print(f" remendo {i}: origem Y={ys:.1f} | entorno Y={statistics.mean(ring):.1f} | diferença {diff:+.1f}{flag}")
        # 2) antes/depois no quadro q, com margem
        m = 40
        cx, cy = max(0, x - m), max(0, y - m)
        cw, ch = min(W - cx, w + 2 * m), min(H - cy, h + 2 * m)
        img = out / f"remendo_{cid}_{i}_antes_depois.jpg"
        pg, lab = patch_graph(patches, q)
        run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex",
             f"[0:v]trim=start_frame={q}:end_frame={q + 1},setpts=PTS-STARTPTS,split[o0][v0]{pg};"
             f"[o0]crop={cw}:{ch}:{cx}:{cy}[a];[{lab}]crop={cw}:{ch}:{cx}:{cy}[b];[a][b]vstack,"
             f"scale=iw*{2 if cw < 640 else 1}:-2[o]", "-map", "[o]", "-frames:v", "1", "-q:v", "2", str(img)])
        print(f"   antes/depois: {img}")
        # 3) quadro a quadro na entrada/saída do remendo
        for edge in ("desde", "ate"):
            if p.get(edge) is not None:
                f0 = max(0, p[edge] - 6)
                strip = out / f"remendo_{cid}_{i}_{edge}.jpg"
                patched_frames(f0, min(10, last - f0 + 1), strip, f"crop={cw}:{ch}:{cx}:{cy},scale=360:-2", 5)
                print(f"   quadros q{f0}–q{f0 + 9} em volta de '{edge}' (já remendados): {strip}")
    # 4) sobreposição entre remendos vizinhos
    for i in range(len(patches)):
        for j in range(i + 1, len(patches)):
            p1, p2 = patches[i], patches[j]
            ox = min(p1["x"] + p1["w"], p2["x"] + p2["w"]) - max(p1["x"], p2["x"])
            oy = min(p1["y"] + p1["h"], p2["y"] + p2["h"]) - max(p1["y"], p2["y"])
            need = 2 * max(p1.get("borda", 5), p2.get("borda", 5))
            if ox > -need and oy > -need and min(ox, oy) < need:
                print(f" ⚠ remendos {i} e {j} se tocam com sobreposição {min(ox, oy)} px < {need} px (2× borda):"
                      " a costura fica visível — aumente a sobreposição")
    print(" confira as imagens: o texto sumiu? sobrou contorno? algo que passa por cima foi apagado?")


# ------------------------------------------------------------------ render: áudio

def speech_regions(narr: Path, aud: dict, intro: float, last_word: float) -> list[tuple[float, float]]:
    sil = silences(narr, aud["silencio_db"], aud["silencio_min_s"])
    regions, cur = [], 0.0
    for a, b in sil:
        if a > cur:
            regions.append([cur, a])
        cur = b
    if cur < last_word - 0.05:
        regions.append([cur, last_word])
    merged: list[list[float]] = []
    for a, b in regions:
        if merged and a - merged[-1][1] < aud["segurar_pausas_s"]:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(max(0.0, a + intro - aud["ducking_antecipar_s"]), b + intro) for a, b in merged if b - a > 0.05]


def momentary(path: Path, start: float, dur: float) -> list[float]:
    out = run(["ffmpeg", "-v", "error", "-ss", f"{start}", "-t", f"{dur}", "-i", str(path), "-af",
               "ebur128=metadata=1,ametadata=print:key=lavfi.r128.M:file=-", "-f", "null", "-"])
    vals = [float(x) for x in re.findall(r"lavfi.r128.M=(-?[\d.]+)", out)]
    return vals[len(vals) // 20:]


def build_audio(plano: dict, base: Path, vid: dict, aud: dict, total_s: float, work: Path) -> tuple[Path, dict]:
    narr = resolve(base, plano["arquivos"]["narracao"])
    music = resolve(base, plano["arquivos"].get("trilha"))
    sr, intro, last = aud["taxa"], vid["abertura_s"], plano["fim_ultima_palavra"]
    delay = round(intro * 1000)
    voice = work / "voz.wav"
    ch = audio_info(narr)["canais"]
    up = "pan=stereo|c0=c0|c1=c0," if ch == 1 else "aformat=channel_layouts=stereo,"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(narr), "-af",
         f"aresample={sr}:resampler=soxr,{up}adelay={delay}|{delay},apad=whole_dur={total_s},atrim=0:{total_s}",
         "-c:a", "pcm_f32le", str(voice)])
    speech = (intro, last)
    v = loudness(voice, *speech)
    stats: dict = {"voz_I": v["I"]}
    mix = voice
    if music:
        bed = work / "trilha.wav"
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{aud['trilha_inicio_s']}", "-t", f"{total_s}", "-i", str(music),
             "-af", f"aresample={sr}:resampler=soxr,aformat=channel_layouts=stereo,afade=t=in:d={vid['fade_in_s']},"
                    f"afade=t=out:st={total_s - vid['fade_out_s']}:d={vid['fade_out_s']},apad=whole_dur={total_s},"
                    f"atrim=0:{total_s}", "-c:a", "pcm_f32le", str(bed)])
        key = voice
        if aud["segurar_pausas_s"] > 0:
            key = work / "chave_ducking.wav"
            regions = speech_regions(narr, aud, intro, last)
            rms_db = 20 * math.log10(aud["ducking_limiar"]) + aud["ducking_profundidade_db"] / (1 - 1 / aud["ducking_ratio"])
            amp = 10 ** (rms_db / 20) * math.sqrt(2)
            gate = "+".join(f"between(t,{x:.3f},{y:.3f})" for x, y in regions)
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                 f"aevalsrc=exprs='{amp:.6f}*sin(2*PI*1000*t)*gt({gate},0)':s={sr}:d={total_s}",
                 "-af", "pan=stereo|c0=c0|c1=c0", "-c:a", "pcm_f32le", str(key)])
        sc = (f"threshold={aud['ducking_limiar']}:ratio={aud['ducking_ratio']}:"
              f"attack={aud['ducking_ataque_ms']}:release={aud['ducking_release_ms']}")

        def duck(gain: float, out: Path) -> None:
            run(["ffmpeg", "-v", "error", "-y", "-i", str(bed), "-i", str(key), "-filter_complex",
                 f"[0:a]volume={gain:.2f}dB[m];[m][1:a]sidechaincompress={sc}[d]", "-map", "[d]",
                 "-c:a", "pcm_f32le", str(out)])

        # o ganho do ducking depende só da chave → o nível da trilha escala 1:1 com o ganho dela
        probe_f = work / "trilha_duck_teste.wav"
        duck(0.0, probe_f)
        gain = (v["I"] - aud["musica_abaixo_da_voz_db"]) - loudness(probe_f, *speech)["I"]
        ducked = work / "trilha_duck.wav"
        duck(gain, ducked)
        d = loudness(ducked, *speech)
        raw = loudness(bed, *speech, pre=f"volume={gain:.2f}dB,")
        def spread(vals: list[float]) -> float:
            vs = sorted(vals)
            return vs[int(len(vs) * .95)] - vs[int(len(vs) * .05)]
        bed_g = work / "trilha_ganho.wav"
        run(["ffmpeg", "-v", "error", "-y", "-i", str(bed), "-af", f"volume={gain:.2f}dB", "-c:a", "pcm_f32le", str(bed_g)])
        var_duck = spread(momentary(ducked, intro + 0.5, last - 0.5))
        var_raw = spread(momentary(bed_g, intro + 0.5, last - 0.5))
        voice_med = statistics.median(momentary(voice, intro + 0.5, last - 0.5))
        open_m = max(momentary(ducked, 0.0, intro)) if intro >= 0.5 else None
        end_w = total_s - vid["fade_out_s"] - (intro + last)
        end_m = max(momentary(ducked, intro + last + 0.2, max(end_w - 0.2, 0.4)))
        stats.update({"trilha_ganho_dB": gain, "trilha_sem_ducking_I": raw["I"], "trilha_com_ducking_I": d["I"],
                      "voz_menos_trilha_dB": v["I"] - d["I"],
                      # integrado na janela de fala; não é o ajuste ducking_profundidade_db
                      "reducao_ducking_medida_dB": raw["I"] - d["I"],
                      "trilha_variacao_sob_voz_dB": var_duck,          # p95−p5 da loudness momentânea
                      "trilha_variacao_propria_dB": var_raw,           # a mesma medida sem ducking
                      "bombeamento_dB": var_duck - var_raw,            # ≈0 = sem bombeamento
                      "trilha_abertura_vs_voz_dB": (open_m - voice_med) if open_m is not None else None,
                      "trilha_final_vs_voz_dB": end_m - voice_med,
                      "ducking_modo": "envelope" if aud["segurar_pausas_s"] > 0 else "literal"})
        mix = work / "mix.wav"
        run(["ffmpeg", "-v", "error", "-y", "-i", str(voice), "-i", str(ducked), "-filter_complex",
             "[0:a][1:a]amix=inputs=2:normalize=0:duration=first[a]", "-map", "[a]", "-c:a", "pcm_f32le", str(mix)])
    m = loudness(mix)

    # ganho estático + limitador sobreamostrado 4x; teto baixa se o AAC passar do pico
    lim, aac = work / "mix_lim.wav", work / "audio_final.m4a"
    ceiling = aud["teto_limitador_db"]
    for _ in range(5):
        mg = aud["alvo_lufs"] - m["I"]
        for _ in range(6):
            run(["ffmpeg", "-v", "error", "-y", "-i", str(mix), "-af",
                 f"volume={mg:.3f}dB,aresample={sr * 4}:resampler=soxr,alimiter=limit={10 ** (ceiling / 20):.5f}:"
                 f"attack=5:release=50:level=0,aresample={sr}:resampler=soxr", "-c:a", "pcm_f32le", str(lim)])
            r = loudness(lim)
            if abs(r["I"] - aud["alvo_lufs"]) <= 0.03:
                break
            mg += aud["alvo_lufs"] - r["I"]
        run(["ffmpeg", "-v", "error", "-y", "-i", str(lim), "-c:a", "aac", "-b:a", aud["aac"], "-ar", str(sr), str(aac)])
        fa = loudness(aac)
        if fa["TP"] <= aud["alvo_tp"] and abs(fa["I"] - aud["alvo_lufs"]) <= 0.1:
            break
        ceiling -= max(0.2, fa["TP"] - aud["alvo_tp"] + 0.1)
    else:
        print("  ⚠ não convergiu para o alvo de loudness/pico — confira as medições")
    peaks = [float(x) for x in re.findall(r"Peak_level=(-?[\d.]+)", run(
        ["ffmpeg", "-v", "error", "-i", str(mix), "-af", f"volume={mg:.3f}dB,asetnsamples=n={sr // 10},"
         "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level:file=-", "-f", "null", "-"]))]
    over = [p - ceiling for p in peaks if p > ceiling]
    stats.update({"mix_antes_I": m["I"], "ganho_master_dB": mg, "teto_limitador_dB": ceiling,
                  "limitador_janelas_pct": 100 * len(over) / max(1, len(peaks)),
                  "limitador_reducao_media_dB": sum(over) / max(1, len(over)),
                  "limitador_reducao_max_dB": max(over, default=0.0)})
    return aac, stats


# ------------------------------------------------------------------ render: final

def review_sheet(video: Path, segs: list[dict], fps: float, out: Path, work: Path) -> None:
    tiles = []
    for s in segs:
        for k, f in enumerate((s["inicio"] + 1, s["inicio"] + s["n"] // 2, s["inicio"] + s["n"] - 1)):
            png = work / f"rev_{s['idx']:02d}_{k}.png"
            run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                 f"select='eq(n,{f})',scale=426:240:force_original_aspect_ratio=decrease,"
                 f"pad=426:240:(ow-iw)/2:(oh-ih)/2,drawtext=text='{s['idx']} {s['clipe']} {f / fps:.2f}s':"
                 "x=6:y=6:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6", "-frames:v", "1", str(png)])
            tiles.append(png)
    args = sum((["-i", str(t)] for t in tiles), [])
    layout = "|".join(f"{c * 426}_{r * 240}" for r in range(len(segs)) for c in range(3))
    run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex",
         f"{''.join(f'[{i}:v]' for i in range(len(tiles)))}xstack=inputs={len(tiles)}:layout={layout}[o]",
         "-map", "[o]", "-q:v", "3", str(out)])


def cmd_render(a: argparse.Namespace) -> None:
    pp = Path(a.plano).resolve()
    plano, base, vid, aud, ctx = load_plan(pp)
    segs, total = timeline(plano, vid, ctx)
    fps, total_s = vid["fps"], total / vid["fps"]
    out_dir = Path(a.saida).resolve() if a.saida else base
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(a.trabalho).resolve() if a.trabalho else base / "_trabalho"  # fora da entrega
    work.mkdir(parents=True, exist_ok=True)
    name = plano.get("nome", "video_final")
    final = out_dir / f"{name}.mp4"

    print("[vídeo]")
    video = build_video(plano, vid, ctx, segs, total, work)
    print("[áudio]")
    audio, stats = build_audio(plano, base, vid, aud, total_s, work)
    print("[codificação final]")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(audio), "-vf",
         f"fade=t=in:st=0:d={vid['fade_in_s']},fade=t=out:st={total_s - vid['fade_out_s']}:d={vid['fade_out_s']}",
         "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", str(vid["crf"]),
         "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(final)])

    fl = loudness(final)
    stats.update({"final_I": fl["I"], "final_TP": fl["TP"], "final_LRA": fl["LRA"],
                  "final_quadros": count_frames(final), "quadros_esperados": total,
                  "resolucao": f"{vid['largura']}x{vid['altura']}", "fps": fps, "duracao_s": total_s})
    review_sheet(final, segs, fps, out_dir / f"{name}_revisao.jpg", work)
    (out_dir / "medicoes.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False))
    (out_dir / "mapa_de_corte.md").write_text(map_table(segs, fps, plano) + "\n")
    # entrega reproduzível: script + plano com caminhos absolutos (o relativo quebra ao copiar)
    if Path(__file__).resolve() != (out_dir / "montagem.py").resolve():
        (out_dir / "montagem.py").write_text(Path(__file__).read_text())
    deliv = json.loads(pp.read_text())
    deliv["arquivos"]["clipes"] = {k: str(resolve(base, v)) for k, v in deliv["arquivos"]["clipes"].items()}
    for k in ("narracao", "trilha"):
        if deliv["arquivos"].get(k):
            deliv["arquivos"][k] = str(resolve(base, deliv["arquivos"][k]))
    if deliv.get("analise"):
        deliv["analise"] = str(resolve(base, deliv["analise"]))
    if pp.resolve() != (out_dir / "plano.json").resolve():
        (out_dir / "plano.json").write_text(json.dumps(deliv, indent=1, ensure_ascii=False))
    print("\nMEDIÇÕES")
    for k, val in stats.items():
        print(f"  {k}: {val:.2f}" if isinstance(val, float) else f"  {k}: {val}")
    for s in segs:
        for w in s["avisos"]:
            print(f"  ⚠ trecho {s['idx']} ({s['clipe']}): {w}")
    print(f"\nok: {final} | {name}_revisao.jpg | medicoes.json | mapa_de_corte.md | plano.json | montagem.py"
          f"\n    (arquivos intermediários em {work} — não fazem parte da entrega)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("analisar")
    p.add_argument("--clipes", nargs="+", required=True)
    p.add_argument("--narracao", required=True)
    p.add_argument("--trilha")
    p.add_argument("--saida", required=True)
    p.add_argument("--nome")
    p.add_argument("--ordenar", choices=["lista", "horario", "nome"], default="lista",
                   help="ordem dos IDs: como passados, pelo carimbo de data/hora no nome, ou alfabética")
    p.set_defaults(fn=cmd_analisar)
    p = sub.add_parser("alinhar")
    p.add_argument("plano")
    p.add_argument("--texto", required=True)
    p.set_defaults(fn=cmd_alinhar)
    p = sub.add_parser("plano")
    p.add_argument("plano")
    p.set_defaults(fn=cmd_plano)
    p = sub.add_parser("remendo")
    p.add_argument("plano")
    p.add_argument("--clipe", required=True)
    p.add_argument("--quadro", type=int, help="quadro de origem para o antes/depois (padrão: penúltimo)")
    p.add_argument("--saida", help="pasta das imagens (padrão: pasta do plano)")
    p.set_defaults(fn=cmd_remendo)
    p = sub.add_parser("render")
    p.add_argument("plano")
    p.add_argument("--saida")
    p.add_argument("--trabalho", help="pasta de intermediários (padrão: <pasta do plano>/_trabalho)")
    p.set_defaults(fn=cmd_render)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
