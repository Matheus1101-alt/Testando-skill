# Chernobyl — colagem de papel (montagem sincronizada)

## Arquivos

| Arquivo | O que é |
|---|---|
| `colagem.mp4` | 1280×720, 24 fps, H.264 High (CRF 18), AAC 48 kHz estéreo (~200 kbps), +faststart. 67,54 s (1621 quadros), 35 MB. |
| `colagem_revisao.jpg` | Início, meio e fim de cada trecho. |
| `plano.json` + `montagem.py` | Para refazer: `python3 montagem.py render plano.json`. Em outra máquina, troque os caminhos em `arquivos` (clipes, narração, trilha). |
| `medicoes.json`, `mapa_de_corte.md` | Números e mapa gerados pelo render. |

## Mapa de corte final
Os clipes foram reordenados pelo conteúdo; a ordem de geração (C01…C14, pelo carimbo de hora) não seguia a narração.

| # | Tempo (s) | Narração | Clipe (quadros) | Velocidade | Congelamento |
|---|---|---|---|---|---|
| 1 | 0,00–8,67 | 1. 26 de abril de 1986, usina nuclear de Chernobyl, Ucrânia Sov | C05 (18–143) | 0.73x | 1.5 s abertura |
| 2 | 8,67–14,50 | 2. À 1h23 da madrugada, um operador do Reator 4 aperta o botão  | C04 (4–95) | 0.67x | 0.12 s |
| 3 | 14,50–17,12 | 3. O botão encerrava um teste de segurança. | C14 (10–68) | 0.94x | — |
| 4 | 17,12–24,58 | 4. Queriam saber se as turbinas, ao desacelerar, ainda alimenta / 5. O teste já atrasara 10 horas. | C01 (1–134) | 0.75x | — |
| 5 | 24,58–31,92 | 6. Durante a preparação, a potência caiu abaixo do previsto. / 7. Os operadores retiraram quase todas as barras de controle pa | C02 (12–143) | 0.75x | — |
| 6 | 31,92–34,17 | 8. Isso deixou o reator instável. | C09 (28–77) | 0.93x | — |
| 7 | 34,17–37,33 | 9. Quando o botão foi pressionado, a potência disparou. | C10 (58–134) | 1.01x | — |
| 8 | 37,33–39,96 | 10. Duas explosões abriram o teto do prédio. | C08 (22–85) | 1.02x | — |
| 9 | 39,96–43,71 | 11. Em minutos, bombeiros chegaram para combater o fogo no telha | C06 (4–65) | 0.69x | — |
| 10 | 43,71–50,50 | 12. Nenhuma evacuação foi ordenada naquela noite. / 13. Pripyat, a cidade vizinha, só foi esvaziada na tarde seguint | C12 (9–143) | 0.83x | — |
| 11 | 50,50–54,79 | 14. Cerca de 49 mil pessoas partiram com poucos pertences. | C03 (30–132) | 1.00x | — |
| 12 | 54,79–59,04 | 15. Dois dias depois, sensores de uma usina sueca detectaram a r | C11 (52–143) | 0.90x | — |
| 13 | 59,04–61,75 | 16. Só então Moscou reconheceu o acidente. | C07 (24–67) | 0.68x | — |
| 14 | 61,75–67,54 | 17. O combustível derretido ainda está lá embaixo. | C13 (50–143) | 0.68x | — |

## Áudio: medições
- Fontes: narração TTS -18,2 LUFS mono (-15,2 em estéreo), 24 kHz; trilha "Honor and Sword" (good_b_music) -10,8 LUFS, pico +0,2 dBTP (**clipada na origem**), 3 s de silêncio inicial; usada a partir de 10 s, onde ganha corpo.
- Música sob a voz: 12,0 dB abaixo; bombeamento 0,0 dB (variação sob a voz 5,0 dB contra 5,0 dB da própria faixa — a variação é da música, não do ducking); ducking por envelope fala/pausa, redução medida 7,0 dB.
- Abertura e final: música a -6,8 / -1,6 dB do nível da voz (profundidade do ducking reduzida de 8 para 5 dB; com 8 dB a música passava 1,4 dB acima da voz no final).
- Congelado no total: 0,1 s (0 % do vídeo, sem a abertura de 1,5 s).
- Mixagem final: -14,0 LUFS, -2,0 dBTP (medido no AAC), LRA 3,4.
- Limitador: atua em 22 % das janelas de 100 ms, média de 1,2 dB, máximo de 3,3 dB. Trabalho leve.
- **Avaliação feita só por medição; o áudio não foi ouvido.**

## Onde me afastei do pedido literal, e por quê
1. **Ordem dos clipes:** reordenados pelo conteúdo da narração, não pela ordem de envio/geração.
2. **Transcrição local (Whisper) em vez de ElevenLabs:** sem custo de créditos e com tempo por palavra. Corrigi 6 inícios de frase que o `alinhar` marcou 0,3–0,4 s cedo (pausas partidas por respiro).
3. **Trilha começa em 10 s da faixa** (não em 0): os primeiros 3 s são silêncio e 3–10 s é introdução fraca.
4. **Ducking mais raso na abertura/final** (5 dB em vez de 8) — ver medições.
5. **Áudio próprio dos clipes descartado** (efeitos de papel, -30 a -38 LUFS).

## Pontos fracos que ficaram
### Falta de imagem
- **Frase 17** ("combustível derretido ainda está lá embaixo"): comboio + carimbo ZONA DE EXCLUSÃO. Fecho temático, não ilustração literal.
- **Frase 15** ("sensores de uma usina sueca"): avião soviético e fio vermelho pela Europa. Lê-se como "a radiação viajou", não como "sensores suecos".
- **Frase 3** ("o botão encerrava um teste de segurança"): turbina, porque o teste era da turbina. Indireto.
- **Frase 7** ("retiraram quase todas as barras"): no C02 as barras **descem e entram** no bloco — o movimento contradiz a fala para quem prestar atenção.
- Frases 4+5, 6+7 e 12+13 dividem um clipe cada; a sincronia interna funciona (etiqueta ATRASO DE 10 HORAS entra ~0,4 s antes da frase 5; barras entram em "barras de controle"; ônibus chegam em "Pripyat").
- Trecho 13 (C07): o primeiro ~1,3 s é o mapa vazio antes de as autoridades entrarem.
### Trechos esticados, acelerados ou congelados
- Trecho 2 (C04): 0,67x + 0,12 s congelado — para acabar antes do carimbo GLISTECA.
- Trecho 9 (C06): 0,69x — para acabar antes de "an l sior unit".
- Trecho 13 (C07): 0,68x — para acabar antes de "ACCEPTED"/"LUCCEPTED".
- Trecho 14 (C13): 0,68x — para o carimbo final entrar antes do fade-out.
- Trecho 6 (C09): 2,2 s, abaixo dos 2,5 s recomendados — a frase 8 só dura isso.
- Em colagem de papel, a cadência mais lenta combina com o estilo; não há congelamento perceptível.
### Erros de texto e de conteúdo visíveis
- **C04, 8,7–14,5 s (o pior do vídeo; mantido por decisão sua):** "EMEMERGÊNCIA" no anel do botão (8,7–10,0 s e 11,7–14,5 s); "PPARADA DE EMERGÊNCICIA" a partir de 12,0 s; relógio marcando 10:10 ao lado da etiqueta "01:23" a partir de 13,2 s; bilhete sem sentido ("…thetespertação perras.") a partir de 13,5 s.
- C08, 37,3–40,0 s: recortes de jornal falsos e pequenos ("inkent im", "NEW SHEET").
- C06, 43,3–43,7 s: etiqueta "REACTOR SITE" (inglês, mas correta).
- C07, 59,0–61,8 s: etiqueta pequena "srore flaugits" no topo.
- C11, 54,8–59,0 s: carimbo pequeno espelhado ("TIABIAD") no rodapé.
- Narração: o Whisper ouviu "Só então **o** Moscou" (57,6 s de narração). Se o TTS falou assim, é erro de dicção que a edição não corrige.
- Fatos da narração conferidos: todos corretos.
### Áudio
- Trilha clipada na origem (+0,2 dBTP); o limitador final absorve, mas a distorção que já está no MP3 continua lá.
- Narração TTS a 24 kHz (banda limitada a 12 kHz) — normal para TTS, nota-se em fone bom.
- Caráter da trilha (épico/marcial) não avaliado de ouvido.
### Licença da trilha
- "Honor and Sword" de good_b_music parece ser da Pixabay (Pixabay Content License: uso comercial sem atribuição). Confirme a origem. Faixas da Pixabay às vezes estão registradas no Content ID do YouTube; guarde o link e a data do download para contestar uma reivindicação.

## Clipes novos que valem a pena (em ordem de prioridade)
1. **Frase 2 / 6 s — refazer C04:** "paper collage animation: black-and-white cutout of a 1980s Soviet control-room operator in a white coat pressing a large red mushroom-head emergency button on a grey control panel; a round wall clock showing 1:23; no readable text, no labels, no stamps". (A etiqueta 01:23 pode ser adicionada na edição.)
2. **Frase 17 / 6 s:** "paper collage animation: cross-section cutout of a concrete reactor building under a large curved steel arch, a dark solidified lava-like mass glowing faintly in the basement; no readable text".
3. **Frase 15 / 5 s:** "paper collage animation: cutout of a Swedish nuclear power plant by the sea, a worker in white coveralls holding a radiation detector with a needle gauge, a red thread arriving from the east across a map of the Baltic; no readable text".
