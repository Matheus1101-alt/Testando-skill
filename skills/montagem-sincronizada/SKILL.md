---
name: montagem-sincronizada
description: Monta vídeo narrado a partir de clipes curtos gerados por IA (Veo, Kling, Runway, Sora, Hailuo etc.) + narração + trilha opcional. Associa cada clipe à frase que ele ilustra, ajusta velocidade e congelamento dentro de limites, mostra plano de corte para aprovação, renderiza com ffmpeg, aplica ducking, normaliza para -14 LUFS e entrega MP4 + relatório honesto dos pontos fracos + script para refazer. Use sempre que o usuário mandar vários clipes e uma narração e pedir para editar, montar, sincronizar, juntar ou "fazer o vídeo", de qualquer nicho (história, true crime, ciência, finanças, curiosidades, religião, biografias) e estética (colagem de papel, stop-motion, ilustração, 3D, cinematográfico, vertical para Shorts/Reels/TikTok). Use também para refazer ou ajustar um vídeo montado assim, ou para descobrir quais clipes faltam gerar para cobrir uma narração. Não use para editar apresentador falando para a câmera, cortar podcast ou só legendar vídeo pronto.
---

# Montagem sincronizada: clipes de IA + narração + trilha

O resultado é um vídeo em que cada corte cai numa pausa da narração e cada clipe mostra o que a frase diz. A ferramenta `scripts/montagem.py` (dentro desta skill) faz o trabalho mecânico: medir, alinhar, validar e renderizar. O seu trabalho é **olhar** os clipes, decidir o plano de corte com bom senso editorial e **dizer a verdade** sobre o que ficou fraco.

A skill serve para qualquer nicho e assunto. Nada aqui assume um tema. O exemplo em `references/plano_exemplo.json` (Alcatraz) é só ilustração do formato.

Antes de montar o plano, leia `references/licoes.md`. Ela tem os erros reais que esse processo já cometeu, e cada um custou uma rodada de retrabalho.

## O que você precisa

- **Clipes** (vários MP4 curtos), **narração** (WAV/MP3) e, se houver, **trilha**.
- **Texto do roteiro**, se o usuário tiver. Isso dispensa a transcrição paga e evita erros dela.
- ffmpeg/ffprobe ≥ 5 com `sidechaincompress`, `ebur128`, `silencedetect`, libx264 e libsoxr; Python 3.9+. Para conferir: `ffmpeg -hide_banner -filters | grep -E "sidechaincompress|ebur128|silencedetect"`.
- Opcional, mas recomendado: `pip install faster-whisper` (transcrição local grátis, com tempo por palavra; o modelo baixa do Hugging Face na primeira vez).
- Uma pasta de projeto, por exemplo `<nicho>/<titulo>/`, onde ficam `analise/` e a entrega.

`SKILL=<caminho desta skill>`; os comandos abaixo usam `python3 $SKILL/scripts/montagem.py`.

## Etapa 1: Análise (não renderize nada ainda)

**1. Medir.**
```bash
python3 $SKILL/scripts/montagem.py analisar --clipes <clipes> --narracao <narr> [--trilha <trilha>] \
    --saida <projeto>/analise --nome <slug-do-video> [--ordenar horario|nome]
```
Os IDs (C01, C02…) seguem a ordem passada. Com `--ordenar horario`, seguem o carimbo de data e hora no nome do arquivo (ex.: `..._20261003151242.mp4`), que costuma ser a ordem de geração. A ordem de geração **não** é a ordem do vídeo: num projeto de 14 clipes nenhum ficou na posição de geração. O plano reordena pelo conteúdo; diga isso ao usuário quando ele não souber a ordem. O áudio próprio dos clipes é descartado; avise se algum clipe tiver som que o usuário talvez queira manter. O comando gera `analise.json`, `plano.json` (esqueleto), `folha_de_contato.jpg` e `grade_Cxx.jpg` (1 quadro/s, rotulado com o **número do quadro de origem**). Informe ao usuário duração, resolução e fps de cada clipe, a soma comparada com a narração mais cerca de 5 s de abertura e final, e qualquer mistura de resolução ou fps. Fale também do **flash inicial**: geradores image-to-video costumam começar com 2 a 20 quadros da imagem pronta e depois "piscar". O script mostra `sim → q4` (fim do flash: antes disso nunca) e, quando a medida conservadora discorda, `(confira até q28)`. Entre os dois pode haver cena nova, usável (no C04 de um teste era só a troca de painel), ou a imagem pronta se desmontando, que você deve evitar. Decida olhando a grade. Por fim, aponte silêncio inicial e clipping na trilha.

**2. Olhar.** Abra a folha de contato e **todas** as grades. Descreva cada clipe em uma linha e anote em que quadro o elemento-chave aparece e em que quadro a cena assenta. O plano inteiro depende disso.

**3. Caçar problemas de texto e conteúdo.** Geradores de vídeo erram texto com muita frequência (7 de 10 clipes no primeiro projeto). Para cada clipe, liste com o intervalo de quadros:
- palavras sem sentido ou em outro idioma, documentos e jornais falsos, carimbos ilegíveis;
- contagens erradas (riscos contra a etiqueta), calendários impossíveis, números sem contexto;
- objetos que contradizem a narração (por exemplo, "colete" desenhado como colete social em vez de salva-vidas).

Quando a grade de 1 quadro/s não basta para delimitar um problema, extraia quadros mais próximos. Desenhe o rótulo **antes** do `select`, para o número ser o de origem:
```bash
ffmpeg -v error -i CLIP.mp4 -vf "scale=480:-2,drawtext=text='%{n}':x=6:y=6:fontsize=24:fontcolor=white:box=1:boxcolor=black,select='between(n,60,84)*not(mod(n,3))',tile=3x3" -frames:v 1 out.jpg
```

**4. Transcrever e alinhar.**
Ordem de preferência:
1. **Whisper local** (grátis, com tempo por palavra), se `faster-whisper` estiver instalado ou instalável:
   ```bash
   python3 $SKILL/scripts/montagem.py transcrever <projeto>/analise/plano.json [--roteiro roteiro.txt]
   ```
   Gera `palavras.json` e `transcricao_whisper.txt`. Rode **mesmo quando o usuário mandou o roteiro**: com `--roteiro`, ele compara palavra a palavra e mostra onde o áudio diverge do texto. Num teste, pegou "Só então **o** Moscou", um erro de dicção do TTS que a edição não corrige e que o usuário precisa saber. Números escritos com algarismos ("1986") e nomes próprios geram falsos alarmes; ignore esses.
   - O texto para o `alinhar` é o roteiro do usuário, se houver. Se não houver, use `transcricao_whisper.txt` revisado: corrija nomes e números e confira a pontuação, porque o `alinhar` divide frases por `. ! ?`.
2. **Roteiro sem Whisper:** salve como `transcricao.txt`. Para conferir se ele bate com o áudio sem pagar transcrição, use o `alinhar`: com o texto certo, a velocidade de fala fica coerente (nenhuma linha com ⚠) e cada frase cai numa pausa clara. Várias linhas com ⚠, ou o erro "há N frases mas só M pausas", indicam que o texto não é o que foi gravado. Pergunte ao usuário antes de seguir.
3. **ElevenLabs (MCP)**, só se não houver roteiro nem Whisper, nesta ordem:
  1. `creative_create_flow`.
  2. `creative_create_asset_upload` com nome, mime e tamanho exato em bytes.
  3. `curl -X PUT -H "Content-Type: <mime>" --data-binary @arquivo "<upload_url>"`.
  4. `creative_finalize_asset_upload` com `flow_id`.
  5. `creative_transcribe_audio` (`eleven_scribe_v1`, `connect_from=[node_id]`).
  6. `creative_get_flow_run_status` até concluir.

  Custa cerca de 14 créditos por segundo de áudio e volta **sem tempo por palavra**. Por isso existe o `alinhar`. Não repita a chamada para "tentar de novo": cada chamada cobra outra vez.
- Rode `python3 $SKILL/scripts/montagem.py alinhar <projeto>/analise/plano.json --texto transcricao.txt [--palavras <projeto>/analise/palavras.json]`. Ele divide o texto em frases e escolhe as pausas por programação dinâmica, buscando velocidade de fala coerente e preferindo pausas longas. Confira as linhas marcadas com ⚠.
- **Use `--palavras` sempre que tiver o Whisper.** Respiros e estalos curtos logo depois de uma pausa partem a pausa em duas, e o início da frase cai 0,3 a 0,4 s cedo. Num teste isso aconteceu em 6 de 17 frases. Com `--palavras`, o `alinhar` corrige sozinho (`[respiro: 12.80→13.09]`) e marca com ⚠ o que não sabe resolver. O Whisper erra até ~0,3 s, então um ⚠ isolado sem pausa candidata costuma ser imprecisão dele, não do alinhamento. Se a narração tiver frases muito longas, você pode dividi-las numa pausa interna editando `frases` no plano.
- Confira os **fatos** da narração e aponte qualquer erro. O usuário quer saber, mesmo sem ter pedido.

## Etapa 2: Plano de corte (mostre e espere aprovação)

Preencha `cortes` no `plano.json`. Cada item é `{"frase": n, "clipe": "Cxx", "de": q_inicial, "ate": q_final, "nota": "..."}`. O trecho vai do início da frase `n` até o início da frase do item seguinte. Os quadros são do clipe de origem (quadro = segundo × fps).

O primeiro corte sempre começa em 0 e inclui a abertura. O quadro parado da abertura é o quadro `de` do primeiro corte, então escolha esse quadro pensando também em como ele fica parado com fade-in.

Como escolher:
- **Pelo conteúdo, não pela ordem de envio.** Se a narração é cronológica, reordene os clipes.
- **Um clipe para duas frases, com o evento interno caindo na segunda.** Quando um clipe monta algo no meio (uma etiqueta, um carimbo, um objeto entrando), escolha `de`, `ate` e a velocidade para que esse quadro caia logo antes da frase que ele ilustra. Confira com `plano --onde C01:87`, que diz o segundo em que o quadro aparece e quanto falta para a próxima frase. Num teste: a etiqueta "ATRASO DE 10 HORAS" entrou 0,4 s antes de "O teste já atrasara 10 horas", e as barras de controle entraram em "barras de controle", sem corte novo.
- **Escolha `ate` olhando quadro a quadro, não pela grade.** A grade de 1 quadro/s e as ampliações a cada 6 quadros não mostram um rótulo que entra 1 a 5 quadros antes do `ate`. Num teste, 4 trechos terminavam com texto sem sentido recém-entrado e só a folha de revisão do render mostrou. Agora o `bordas` (abaixo) pega isso antes de renderizar.
- **Uma frase por clipe** quando possível. Uma janela curta (menos de 2,5 s) se junta à frase vizinha.
- **Escolha do trecho do clipe:**
  - comece em `inicio_seguro_quadro` ou depois, nunca no flash;
  - fuja dos intervalos com texto ruim;
  - mostre o elemento-chave, que normalmente fica no final, onde a cena já montou;
  - prefira cortar o trecho e manter 1x. Acelere (até 1,33x) só quando a montagem da cena for o ponto da frase. Desacelere até 0,67x; abaixo disso o script congela o último quadro.
- **Congelamento somado importa.** Cada congelamento pode ficar abaixo de 3 s e o vídeo ainda parecer parado. Num teste, desviar de todo texto ruim custou 9 s congelados (14% do vídeo) e cinco trechos a 0,67x. O `plano` soma tudo e avisa acima de 8%. Quando fugir de um erro de texto custa muito congelamento, não decida sozinho: mostre as duas opções ao usuário (mais congelado e sem o erro, ou mais fluido com o erro visível).
- **Estética:** em colagem de papel e stop-motion, quadro duplicado combina com o estilo. Em estética cinematográfica ou live-action, duplicar quadro a 0,67x fica travado; mantenha entre cerca de 0,85x e 1,15x e prefira cortar.
- **Cobertura:** liste as frases sem clipe que as ilustre e as repetições de clipe. Para cada lacuna, proponha **o clipe a gerar**: duração necessária, descrição explícita dos objetos (evite palavras ambíguas) e "nenhum texto legível". O texto pode entrar depois, na edição.

Rode `python3 $SKILL/scripts/montagem.py plano <projeto>/analise/plano.json` e itere até não sobrar aviso que você não saiba justificar. Depois rode `python3 $SKILL/scripts/montagem.py bordas <projeto>/analise/plano.json` e **abra `bordas.jpg`**. Cada linha mostra o `de`, o `de+3` e os 8 últimos quadros do trecho (1 a 1, até o `ate`), e por fim, com borda vermelha, o `ate+3`, que fica fora do vídeo e mostra o que está para entrar. Se aparecer texto ruim ou um elemento entrando nos quadros sem borda vermelha, recue o `ate`.

O `plano` também imprime a janela do **fade-out** e o quadro do último clipe em que ele começa. O elemento-chave do fecho (um carimbo, um título) precisa entrar antes disso. Num teste, o carimbo "ZONA DE EXCLUSÃO" só aparecia já escurecendo. Os avisos cobrem velocidade fora dos limites, congelamento acima de 3 s por trecho ou de 8% somado, trecho abaixo de 2,5 s, início dentro do flash, quadro final além do fim do clipe e repetição de clipe. Se aparecer "analise.json não encontrado", os avisos de flash estão desligados: corrija o caminho `analise` no plano.

Mostre ao usuário, sem renderizar:
1. A tabela que o comando `plano` imprime: tempo, narração, clipe (quadros), velocidade, congelamento.
2. Os avisos, as lacunas de cobertura e os clipes novos sugeridos.
3. Os problemas de texto que vão continuar visíveis, e o que dá para remendar.
4. As decisões de áudio: onde a trilha começa e o nível sob a voz.

Depois **espere a aprovação**. Repetir um clipe ou gerar um novo é decisão dele, porque custa tempo e créditos dele.

## Etapa 3: Montagem (depois da aprovação)

**Remendos (opcional)** servem para texto ruim sobre fundo liso, como uma tira de papel em página lisa. O script copia um retângulo de papel limpo do mesmo quadro por cima do texto. Defina em `remendos.Cxx`: `{x, y, w, h, sx, sy, borda, [borda_inferior: false], [desde: q], [ate: q]}`.
- Ache as coordenadas num quadro em resolução cheia, ampliado com `drawgrid`.
- O retângulo precisa cobrir a tira **e a sombra** com folga maior que `borda`. Se não cobrir, o contorno da tira reaparece como fantasma.
- A origem (`sx`, `sy`) deve ser papel liso, sem nada se movendo por ela, e com brilho até cerca de 4 níveis do entorno. Se nenhuma área serve para o retângulo inteiro, divida em dois remendos que se sobreponham pelo menos 2× a `borda`.
- Se algo passa por cima da área (um carimbo, uma mão), use `desde`/`ate` para o remendo só valer quando a área estiver livre.
- Use `borda_inferior: false` para alinhar uma borda seca a uma borda que já existe, como o topo de uma fita adesiva.
- **Confira sempre** com `python3 $SKILL/scripts/montagem.py remendo <plano> --clipe Cxx [--quadro N]`. Ele gera o antes/depois, compara o brilho da origem com o entorno, checa a sobreposição entre remendos e mostra quadro a quadro a entrada e a saída (`desde`/`ate`). A folha de revisão do render não mostra esses poucos quadros.

Não remende texto sobre fundo com textura ou movimento: fica pior que o erro. Nesse caso, recomende gerar o clipe de novo.

**Render:**
```bash
python3 $SKILL/scripts/montagem.py render <projeto>/analise/plano.json --saida <projeto>/entrega [--previa-mb 29]
```
Use `--previa-mb` quando o canal de entrega tiver limite de tamanho. Por exemplo, a ferramenta de envio de arquivos do Claude Code remoto aceita até 30 MiB, e um vídeo de 67 s em 720p com CRF 18 deu 35 MB. A opção gera também `<nome>_previa.mp4` abaixo do limite, subindo o CRF. A versão final continua sendo a `<nome>.mp4`.
Ele gera na entrega `<nome>.mp4`, `<nome>_revisao.jpg`, `medicoes.json`, `mapa_de_corte.md`, uma cópia de `montagem.py` e um `plano.json` com caminhos absolutos, que continua achando os arquivos e a análise. Os intermediários ficam em `<pasta do plano>/_trabalho`, fora da entrega.

**Revise antes de entregar.** Abra `<nome>_revisao.jpg`, que mostra o primeiro, o do meio e o último quadro de cada trecho. Procure flash, texto ruim, saltos e trecho mostrando a coisa errada. No primeiro projeto essa revisão pegou três cortes que começavam no lugar errado. Ela não pega problemas de poucos quadros entre as amostras, como texto aparecendo antes de um remendo entrar; para isso serve o `remendo`. Corrija, renderize de novo e revise de novo. Cada render leva uns 2 a 3 minutos para um vídeo de 1 minuto.

## Etapa 4: Áudio (o render faz; você interpreta e relata)

Os padrões, e por que existem:
- **Voz e trilha medidas no mesmo formato (estéreo).** Narração mono comparada com música estéreo erra a diferença em cerca de 3 dB.
- **Trilha 12 dB abaixo da voz**, medida **depois** do ducking, na janela de fala. Se ajustar o nível antes do ducking, a música some: o ducking sozinho tira de 9 a 15 dB.
- **Chave do ducking = envelope fala/pausa da narração** (`segurar_pausas_s` 1,2 s), mantendo limiar 0,02, ratio 8, ataque 40 ms e release 600 ms. Com a narração crua como chave, a música sobe de 12 a 17 dB em **cada** pausa entre frases, um bombeamento audível. Se o usuário exigir o comportamento literal, use `segurar_pausas_s: 0` e relate o bombeamento medido.
- **Normalização:** ganho fixo mais limitador sobreamostrado 4x, verificando o pico real **depois** do AAC. O `loudnorm` cai no modo dinâmico com voz de pico alto, e o AAC soma cerca de 0,3 dB de pico.
- **Trilha começando onde tem corpo** (`trilha_inicio_s`; o `analisar` sugere um valor), com fade-in junto do vídeo e fade-out nos últimos 2,5 s.

Relate os números de `medicoes.json`:
- `voz_menos_trilha_dB`: a diferença pedida, integrada na janela de fala.
- `bombeamento_dB`: variação da música sob a voz (`trilha_variacao_sob_voz_dB`) menos a variação da própria faixa sem ducking (`trilha_variacao_propria_dB`). Perto de 0 quer dizer que a variação é da música, não do ducking. Acima de cerca de 2 dB, há bombeamento.
- `reducao_ducking_medida_dB`: quanto o ducking tirou, integrado. Não confunda com o ajuste `ducking_profundidade_db`.
- `trilha_abertura_vs_voz_dB` e `trilha_final_vs_voz_dB`: o nível da música sem voz, comparado com a voz. Perto de 0 ou acima, a música fica tão alta quanto a narração. Acima de −1 dB o render avisa e sugere um `ducking_profundidade_db` menor. Num teste, o padrão 8 deu +1,4 dB no final, porque a faixa crescia ali; com 5 ficou em −1,6 dB. Depende da trilha, então confira sempre.
- `limitador_*`: quanto o limitador trabalha nos picos.
- `final_I` e `final_TP`.

Você não ouve o resultado. Diga isso e deixe claro que a avaliação foi só por medição.

## Etapa 5: Entrega

O render já deixa na entrega o MP4, a revisão, `plano.json`, `montagem.py`, `medicoes.json` e `mapa_de_corte.md`. Falta escrever `RELATORIO.md` com `references/relatorio_modelo.md`. Se o usuário for refazer em outra máquina, avise que ele precisa trocar os caminhos em `arquivos` no `plano.json`.

Os intermediários ficam em `_trabalho` (centenas de MB, sem compressão), que já vem com um `.gitignore` próprio. Se for fazer commit, inclua só a pasta de entrega e os arquivos pequenos da análise.

**Trilha chegando depois da aprovação:** rode o `analisar` de novo com `--trilha`, com a mesma `--saida`. Ele preserva frases e cortes do `plano.json` existente e só atualiza `arquivos.trilha` e `trilha_inicio_s`. Antes, a trilha nova era ignorada em silêncio.

Envie os arquivos ao usuário com a ferramenta de arquivos, se houver. Faça commit só se o usuário pediu ou se o ambiente exige.

O relatório **não esconde nada**:
- onde você se afastou do pedido literal, e por quê;
- trechos esticados ou congelados;
- repetições e frases sem imagem própria;
- erros de texto ou conteúdo que continuam visíveis, com o tempo no vídeo;
- trabalho pesado do limitador;
- clipping da trilha na origem;
- dúvidas de licença da trilha.

Licença de trilha: pergunte a origem. Pixabay e bibliotecas parecidas costumam permitir uso comercial sem atribuição, mas a faixa pode estar registrada no Content ID. Sugira guardar o link e a data do download.

## Padrões e onde mudar

Tudo fica em `plano.json`, nas chaves `video` e `audio`. Os padrões estão no topo de `scripts/montagem.py`.

| Chave | Padrão | Para quê |
|---|---|---|
| `video.abertura_s` / `final_s` | 1,5 / 3,5 | quadro parado antes da narração / tempo depois da última palavra |
| `video.antecipar_quadros` | 2 | o corte cai N quadros antes da frase |
| `video.vel_min` / `vel_max` | 0,67 / 1,33 | limites de velocidade |
| `video.aviso_congelamento_total_pct` | 8 | aviso quando o congelamento somado passa dessa % do vídeo |
| `video.fps`, `largura`, `altura` | automático | fps mais comum; menor resolução entre os clipes (nunca aumenta) |
| `video.ajuste` | `crop` | proporções diferentes: `crop` ou `pad` |
| `audio.trilha_inicio_s` | sugerido | ponto da faixa onde a música começa |
| `audio.musica_abaixo_da_voz_db` | 12 | diferença voz − trilha na fala |
| `audio.segurar_pausas_s` | 1,2 | 0 = ducking literal pela narração |
| `audio.ducking_profundidade_db` | 8 | quanto a trilha sobe na abertura e no final em relação à fala (baixe se o render avisar) |
| `audio.alvo_lufs` / `alvo_tp` | -14 / -1,5 | normalização |
