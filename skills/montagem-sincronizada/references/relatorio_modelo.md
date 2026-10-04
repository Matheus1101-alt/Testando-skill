# Modelo de RELATORIO.md

Preencha com os dados do projeto. Seja curto e específico: tempo no vídeo, clipe, número medido. Apague as seções que não se aplicam, menos "Pontos fracos". Se não houver nenhum, diga isso explicitamente.

```markdown
# <Título do vídeo>

## Arquivos

| Arquivo | O que é |
|---|---|
| `<nome>.mp4` | <largura>×<altura>, <fps> fps, H.264 High (CRF 18), AAC 192 kbps 48 kHz estéreo, +faststart. <duração> s (<quadros> quadros), <MB> MB. |
| `<nome>_revisao.jpg` | Início, meio e fim de cada trecho. |
| `plano.json` + `montagem.py` | Para refazer: `python3 montagem.py render plano.json`. O plano define os cortes, os remendos e os ajustes de vídeo e áudio. |
| `medicoes.json`, `mapa_de_corte.md` | Números e mapa gerados pelo render. |

## Mapa de corte final
<colar mapa_de_corte.md>

## Ordem e transcrição
- Ordem dos clipes: <reordenados pelo conteúdo / mantida>; ordem de geração × ordem no vídeo, se o usuário não sabia.
- Transcrição: <roteiro do usuário / Whisper local / ElevenLabs>; inícios conferidos com tempo por palavra: <sim/não>; correções do `alinhar`: <n>.
- Narração × roteiro: <diferenças do `transcrever --roteiro`, com tempo; ou "nenhuma">.
- Fatos da narração: <conferidos / erros encontrados>.

## Áudio: medições
- Fontes: narração <X> LUFS (<mono/estéreo>), trilha <Y> LUFS, pico <Z> dBTP <(clipada na origem?)>, usada a partir de <s> s.
- Música sob a voz: <voz_menos_trilha_dB> dB abaixo; bombeamento <bombeamento_dB> dB (variação sob a voz <trilha_variacao_sob_voz_dB> contra <trilha_variacao_propria_dB> da própria faixa); ducking <modo>, redução medida <reducao_ducking_medida_dB> dB.
- Abertura e final: música a <trilha_abertura_vs_voz_dB> / <trilha_final_vs_voz_dB> dB do nível da voz.
- Congelado no total: <s> s (<%> do vídeo, sem a abertura).
- Mixagem final: <final_I> LUFS, <final_TP> dBTP, LRA <final_LRA>.
- Limitador: atua em <pct>% das janelas de 100 ms, média de <dB>, máximo de <dB>.
- Avaliação feita só por medição; o áudio não foi ouvido.

## Onde me afastei do pedido literal, e por quê
1. <desvio — motivo — como voltar ao literal>

## Pontos fracos que ficaram
### Falta de imagem
- Frase <n> (<tema>): <solução usada>, <por que é fraca>.
### Trechos esticados, acelerados ou congelados
- Trecho <i> (<clipe>): <vel>x + <s> s congelado — <motivo>.
### Erros de texto e de conteúdo visíveis
- <clipe>, <t0–t1 s no vídeo>: <o que aparece>.
### Áudio
- <limitador, clipping da origem, taxa da narração, caráter da trilha não avaliado>
- <música no final/abertura perto do nível da voz e o ajuste feito>
### Erros da narração que a edição não corrige
- <tempo: o que o TTS falou × o que o roteiro diz>
### Licença da trilha
- <origem, condições, risco de Content ID, o que guardar>

## Clipes novos que valem a pena (em ordem de prioridade)
1. <frase / duração>: <descrição sem ambiguidade>; nenhum texto legível.
```
