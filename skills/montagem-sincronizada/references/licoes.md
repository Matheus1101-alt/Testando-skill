# Lições aprendidas

Cada item abaixo aconteceu de verdade num projeto e custou retrabalho. Leia antes de montar o plano de corte.

## Clipes

**1. Flash da imagem de referência.** Clipes image-to-video (Veo e outros) começam com a imagem de entrada pronta e depois "piscam" para o início da animação. Num projeto de 10 clipes, todos tinham isso: 2 quadros na maioria, 7 num clipe, cerca de 20 em dois deles. Se o corte começar no quadro 0, o espectador vê a cena final por um instante, depois tudo some e se remonta.
→ O `analisar` detecta o flash pela queda de densidade de bordas e informa `inicio_seguro_quadro`, e o `plano` avisa quando um corte começa antes dele. Mesmo assim, confira na grade: a detecção é heurística.

**1b. Falso flash por troca de cena.** No C04 de outro projeto, o flash real ia só até o quadro 3, mas o detector antigo apontou q28, porque nesse ponto um painel era trocado por outro mais vazio. Seguir o detector jogaria fora 1 s bom do clipe mais curto do vídeo. Ao contrário, no C09 os quadros 2 a 17 eram a imagem pronta se desmontando (as barras encolhendo): isso não é cena nova e precisa ser evitado.
→ O `analisar` agora dá duas medidas: o fim do flash (primeiro salto forte entre quadros; antes disso nunca) e o início conservador (mínimo de bordas). Quando discordam, mostra `sim → q4 (confira até q28)`, e quem decide é a grade.

**2. Número de quadro errado nas grades.** Uma grade feita com `select` e rótulo `%{n}` desenhado **depois** do `select` numera os quadros selecionados (0, 1, 2…), não os de origem. Isso levou a escolher o quadro 8 achando que era "depois do flash", quando o flash ia até o 20.
→ Desenhe o rótulo **antes** do `select`. As grades do `analisar` já fazem assim (`q48` = quadro 48 do clipe).

**3. Texto ruim é a regra, não a exceção.** Erros encontrados em 7 de 10 clipes:
- frases sem sentido em inglês numa narração em português;
- calendário com "JUNE", junho com dia 31, dia 8 faltando e "223";
- 16 riscos de contagem para uma etiqueta "14 TENTATIVAS";
- carimbos e jornais ilegíveis.

→ Cortar o trecho resolve parte. Às vezes dá para cortar logo antes de a etiqueta errada aparecer e congelar 1 a 2 s, sem passar dos limites. Remendo resolve tira de texto sobre fundo liso. O resto vai para o relatório com o tempo exato, junto com a sugestão de gerar o clipe de novo pedindo "nenhum texto legível".

**4. Palavra ambígua no prompt de geração vira objeto errado.** "Colete salva-vidas" virou colete social; "broca improvisada" virou furadeira elétrica moderna.
→ Na hora de sugerir clipes novos, descreva o objeto sem ambiguidade (material, cor, formato) e, se preciso, em inglês.

**5. Cobertura.** A soma dos clipes pode passar da duração da narração (80 s de clipe para 61 s de fala) e mesmo assim faltar imagem para 3 de 14 frases. Duração não é cobertura.
→ Mapeie frase por frase. Para cada frase sem imagem, decida entre reaproveitar outro clipe, juntar com a frase vizinha ou pedir um clipe novo, e mostre isso no plano.

**6. Um clipe pode servir a duas frases, mas repetir um clipe aparece.** Repetir o mesmo plano 20 s depois é o ponto mais fraco de um vídeo curto. A exceção defensável é abrir e fechar com o mesmo plano, como moldura.

## Remendos

**7. Contorno fantasma.** Um remendo do tamanho exato da tira deixa aparecer a borda e a sombra dela, porque a borda suave mistura o original de volta.
→ Cubra tira e sombra com folga maior que `borda`. Confira com um recorte antes/depois.

**8. Objeto passando por cima.** Um carimbo atravessava a área do remendo por cerca de 1 s. O remendo "apagaria" o carimbo.
→ Use `desde`/`ate` (quadros de origem) para o remendo só valer com a área livre. Avise no relatório se o texto aparece por alguns quadros antes do remendo entrar.

**8b. Brilho da origem e remendos vizinhos.** Num teste, a primeira origem escolhida era 4,6 níveis mais escura que o entorno, e a costura apareceu. A solução foi dividir em dois remendos, e eles precisam se sobrepor pelo menos 2× a `borda`, senão a junção aparece.
→ O comando `remendo` mede a diferença de brilho (avisa acima de 4), checa a sobreposição e mostra quadro a quadro a entrada do remendo.

**9. Borda seca alinhada.** Quando o remendo encosta em algo (uma fita adesiva, por exemplo), borda suave cria degradê no objeto.
→ Use `borda_inferior: false` com a borda exatamente no topo do objeto.

## Áudio

**10. Mono contra estéreo.** Narração mono medida contra música estéreo erra a diferença de nível em cerca de 3 dB. Ao mixar, a voz vira estéreo dual-mono e ganha cerca de 3 dB.
→ O script mede as duas em estéreo.

**11. "10–12 dB abaixo da voz" e ducking somam.** Com limiar 0,02 e ratio 8, o ducking sozinho tira de 9 a 15 dB. Ajustar a trilha 11 dB abaixo **antes** do ducking deixou a música 20 dB abaixo durante a fala, ou seja, inaudível no celular.
→ Calibre o nível **depois** do ducking. O script faz isso: o ganho do ducking depende só da chave, então o nível da trilha muda 1:1 com o ganho.

**12. Bombeamento com a narração crua como chave.** Medido: a música ficava cerca de 20 dB abaixo nas palavras e subia de 12 a 17 dB em cada pausa de 0,5 a 1 s. Somar cópias atrasadas da voz como "hold" não resolveu, porque ainda subia de 4 a 13 dB: o fim das frases é baixo demais.
→ A chave virou o envelope fala/pausa (pausas menores que 1,2 s preenchidas) com nível fixo. Os parâmetros do compressor continuam os pedidos. Para saber se ainda bombeia, compare a variação da música com e sem ducking: o render grava `bombeamento_dB` (variação sob a voz menos variação própria da faixa). No primeiro projeto deu 0,0 dB: os 5 dB de variação eram da própria música.

**13. `loudnorm` em modo dinâmico.** Com a voz de TTS (fator de crista de cerca de 19 dB) indo para -14 LUFS, o `loudnorm` de duas passagens caiu no modo dinâmico. Além disso, o AAC levou o pico de -1,5 para -1,2 dBTP.
→ Ganho fixo mais `alimiter` a 4x de taxa (aproxima o pico real) com teto de -2,3 dB, medindo o pico **no AAC** e baixando o teto se precisar. Relate quanto o limitador trabalha (no primeiro projeto: 24% do tempo, média de 2,3 dB, máximo de 5,8 dB).

**14. Trilha de biblioteca.** Pode vir com silêncio no início (2 a 3 s) e com clipping (+0,2 dBTP).
→ Comece onde ela tem corpo e relate o clipping de origem.

**15. Transcrição sem tempo por palavra.** O `creative_transcribe_audio` do ElevenLabs via MCP devolve só o texto.
→ Use o `alinhar` com as pausas. No primeiro projeto ele acertou as 14 fronteiras de frase. Se o usuário tiver o roteiro, use o roteiro e não gaste créditos.

## Processo

**16. Revise a folha de revisão antes de entregar.** O primeiro render tinha três cortes começando dentro do flash ou com jornal falso na tela. Só a folha com o primeiro, o do meio e o último quadro de cada trecho mostrou isso. Ela, porém, não pega problemas de poucos quadros entre as amostras (num teste, 6 quadros de texto antes de um remendo entrar). Para isso use o `remendo`, ou extraia quadro a quadro.

**17. Você não ouve o áudio.** Toda avaliação de áudio é por medição. Diga isso ao usuário em vez de afirmar que "soa bem".

**18. Fugir de todo texto ruim pode congelar o vídeo.** Num teste, um agente desviou de todos os erros de texto (inclusive de um calendário errado e muito visível) e pagou com 9 s de quadro congelado (14% do vídeo) e cinco trechos a 0,67x. Nenhum congelamento passou de 3 s, então nenhum aviso por trecho disparou.
→ O `plano` soma o congelamento e avisa acima de 8%. A troca entre mais congelamento sem o erro e mais fluidez com o erro visível é do usuário: mostre as duas opções no plano.

**19. Rótulo que entra entre as amostras.** Num projeto, 4 de 14 trechos terminavam 1 a 5 quadros depois de um texto sem sentido entrar ("No ltp", "an l sior unit", o carimbo "LUCCEPTED" e um rótulo no canto). As ampliações a cada 6 quadros não mostraram, e só a folha de revisão do render pegou. Cada rodada custou ~3 min de render.
→ Rode `bordas` antes de renderizar: ele mostra os 8 últimos quadros de cada trecho, 1 a 1, e o `ate+3` em vermelho. No teste, o `bordas` sobre o plano original mostrou os 4 vazamentos.

**20. Elemento-chave entrando durante o fade-out.** O carimbo que fechava o vídeo aparecia já escurecendo, porque o último trecho começava cedo demais no clipe. Nada avisava.
→ O `plano` imprime em que quadro do último clipe o fade-out começa. Ajuste o `de` (ou a velocidade) para o elemento entrar antes, e confira com `--onde`.

**21. Um clipe para duas frases funciona quando o evento interno cai na segunda.** A etiqueta "ATRASO DE 10 HORAS" do clipe da bomba entrou 0,4 s antes de "O teste já atrasara 10 horas", e as barras de controle entraram em "barras de controle". Isso cobriu 3 pares de frases sem repetir clipe nem pedir clipe novo.
→ Calcule com `plano --onde Cxx:q`. Antes desse comando, a conta era feita à mão.

## Transcrição e narração

**22. Whisper local substitui a transcrição paga e dá tempo por palavra.** O `faster-whisper` (modelo medium, CPU, int8) transcreveu 63 s de narração em português na CPU em poucos minutos, sem créditos, e acertou o texto todo.
→ Use o `transcrever`. O ElevenLabs fica só para quando não houver rede para baixar o modelo.

**23. Respiro ou estalo parte a pausa e adianta o início da frase.** Em 6 de 17 frases, o `alinhar` marcou o início 0,3 a 0,4 s cedo. Três casos eram estalos de 1 a 21 ms partindo uma pausa em duas; os outros três eram respiros de 0,1 a 0,2 s. A energia dos respiros do TTS (−20 dB) é parecida com a da fala (−15 dB), então não dá para separar por volume.
→ O `silences` junta pausas separadas por menos de 50 ms, e o `alinhar --palavras` usa o Whisper como juiz para os respiros. No teste, reproduziu sozinho as 6 correções feitas à mão.

**24. O TTS pode falar diferente do roteiro.** O roteiro dizia "Só então Moscou"; o áudio dizia "Só então o Moscou".
→ O `transcrever --roteiro` compara palavra a palavra. Leve a diferença ao usuário, porque a edição não corrige.

## Áudio (continuação)

**25. A música pode ficar mais alta que a voz no final.** Com o padrão `ducking_profundidade_db: 8`, a trilha crescia justamente no fim e ficou +1,4 dB acima da voz depois da última palavra.
→ O render agora avisa acima de −1 dB e sugere um valor. Com 5, ficou em −1,6 dB.

## Processo (continuação)

**26. Trilha que chega depois da aprovação era ignorada.** Rodar o `analisar` de novo com `--trilha` num projeto que já tinha `plano.json` não gravava a trilha: o render sairia sem música, e nada avisava.
→ Agora o `analisar` atualiza `arquivos.trilha` e `trilha_inicio_s` e preserva frases e cortes.

**27. Limite de tamanho na entrega.** O MP4 final (67 s, 720p, CRF 18) teve 35 MB, e a ferramenta de envio de arquivos aceitava até 30 MiB.
→ Use `render --previa-mb 29`, e mantenha a versão final no repositório ou na pasta de entrega.

