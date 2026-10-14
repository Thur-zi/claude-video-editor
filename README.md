# claude-video-editor

**Edite vídeos conversando com o Claude.** Você coloca o vídeo bruto numa pasta, abre o Claude Code ali e
pede, em português normal: *"edita esse vídeo para Reels de até 1 minuto, tira as hesitações e coloca
legenda"*. O Claude transcreve, propõe um plano, espera o seu OK, corta, legenda, anima, confere o próprio
resultado e te entrega um `final.mp4` pronto para Reels, TikTok e Shorts.

Este projeto é um *fork* do [browser-use/video-use](https://github.com/browser-use/video-use) (licença MIT),
adaptado para rodar **de graça e localmente**, inclusive em **PCs Windows simples**, sem nenhuma API paga.

> Status: experimental — feito para testes entre amigos. Feedback é muito bem-vindo (abra uma *issue*).

<p align="center">
  <img src="static/timeline-view.svg" alt="Como o Claude 'lê' o vídeo: miniaturas, forma de onda e palavras com tempo" width="100%">
</p>

## Como funciona

O Claude não "assiste" o vídeo. Ele **lê**:

1. **Transcrição palavra por palavra** (Whisper rodando no seu computador), com o tempo exato de cada
   palavra e das pausas. É assim que ele sabe onde cortar sem picotar palavras.
2. **Imagens sob demanda**: quando precisa decidir algo visual, gera um quadro com miniaturas + forma de
   onda daquele trecho.
3. Ele escreve uma **lista de cortes** (`edl.json`) e o `render.py` monta tudo com ffmpeg.
4. Antes de te mostrar, ele **confere o próprio vídeo** (cortes, estalos de áudio, legenda tampando algo,
   volume) e corrige o que achar.

Você participa o tempo todo: ele propõe a estratégia, você aprova ou muda; depois de cada prévia você
pede ajustes em linguagem natural ("legenda maior", "corta essa frase", "tira o zoom").

## O que ele faz

- ✂️ **Corta hesitações, pausas e repetições** ("éé", "hum", falsas largadas) e escolhe o melhor take.
- 📱 **Formato vertical 9:16** (1080×1920) — recorte central ou vídeo inteiro sobre fundo desfocado.
- 💬 **Legendas animadas palavra por palavra** no estilo "premium" das redes: duas espessuras (palavras-chave
  grandes), fonte Inter Display, blocos centralizados, entrada com fade + desfoque.
- 🙂 **Nunca tampa o rosto**: detecta o rosto automaticamente e a montagem *falha* se algum texto encostar
  nele (ou em áreas que você marcar, como um logo na camiseta).
- 🔎 **Zoom de impacto** por frase, sem cortar o áudio.
- 🎬 **Cartão final animado** (número/data grande que se desenha e preenche, textos em sequência).
- 🔊 **Áudio pronto para redes**: tratamento de voz de celular (graves, ruído, presença, compressão) e volume
  em −14 LUFS. Efeitos sonoros (whoosh, pop, impacto) **gerados por código**, sem baixar nada.
- 🎨 **Acabamento de imagem**: ampliação de qualidade para vídeos de baixa resolução, correção leve de cor.
- 🧠 **Manual de edição embutido** (`references/short-form-playbook.md`): pesquisa sobre gancho, ritmo,
  legenda, áreas seguras das plataformas, tempos de animação, som e o que deixa vídeo "com cara de amador".
- 🧩 **Copia o estilo de um vídeo de referência**: mede posição/tamanho da legenda, tempos de animação e
  identifica a fonte (`helpers/extract_logo.py` recorta um logo seu de um vídeo de referência).

## Novo: profundidade, recorte e 3D

Para o vídeo não ficar "chapado", o editor separa cada quadro em **camadas reais**:

```
fundo  →  elementos ATRÁS da pessoa  →  a PESSOA recortada  →  elementos NA FRENTE  →  legenda
```

- ✂️ **Recorte de pessoa** por IA (`helpers/segment.py`) → **texto atrás da pessoa** (ela passa na frente do
  título), troca/desfoque de fundo, e **cartão final em profundidade** (a pessoa "descola" do vídeo como um
  adesivo com contorno e sombra, sobre o fundo da marca).
- 🧊 **3D a partir de qualquer logo ou texto** (`helpers/vectorize.py` + `motion3d/`): extrusão com bisel,
  material e luz, entrada girando, flutuação, giro ou balanço — renderizado com three.js no seu próprio Chrome,
  com fundo transparente.
- ✋ **Objetos presos à mão** (`helpers/hands.py`): o 3D flutua sobre a mão de quem fala e acompanha o movimento.
- 📷 **Foto 2.5D** (`helpers/depth.py` + `motion3d/parallax.html`): um quadro parado ganha volume com um
  movimento de câmera.

Ative com:

```bash
.venv/Scripts/python helpers/get_models.py      # modelos de IA (~60 MB)
.venv/Scripts/python -m pip install mediapipe   # só para o rastreamento de mão
cd motion3d && npm install                      # motor 3D (precisa de Node.js; usa o Chrome/Edge instalado)
```

Exemplos em `motion3d/examples/`. Tudo roda em CPU: recorte ~1–3 s por quadro, 3D ~40–150 ms por quadro.

## Requisitos

- [Claude Code](https://claude.com/claude-code) (app desktop ou terminal) com uma conta Claude.
- Python 3.10+ e ffmpeg.
- ~2 GB livres (dependências + modelo do Whisper). Roda em CPU; não precisa de placa de vídeo.
- Testado em Windows 11 (i5 de 2 núcleos, 8 GB de RAM). Deve funcionar em macOS/Linux.

## Instalação (o jeito fácil)

Abra o Claude Code e cole:

```text
Instale o https://github.com/Thur-zi/claude-video-editor para mim. Leia o install.md e siga os passos:
clonar, criar o ambiente Python, instalar o ffmpeg, registrar a skill e configurar o .env.
Depois me avise que está pronto — não transcreva nada sozinho.
```

O Claude faz tudo e só te pergunta antes de instalar programas no sistema.

### Instalação manual

```bash
git clone https://github.com/Thur-zi/claude-video-editor
cd claude-video-editor
python -m venv .venv
.venv/Scripts/python -m pip install -e .      # Windows  (macOS/Linux: .venv/bin/python)
cp .env.example .env
```

Instale o ffmpeg (`winget install Gyan.FFmpeg` no Windows, `brew install ffmpeg` no Mac) e registre a skill:

```bash
# Windows (Prompt de Comando)
mklink /J "%USERPROFILE%\.claude\skills\claude-video-editor" "C:\caminho\para\claude-video-editor"
# macOS / Linux
ln -sfn "$(pwd)" ~/.claude/skills/claude-video-editor
```

**Windows:** se aparecer erro de DLL ao transcrever, instale o *Microsoft Visual C++ Redistributable*
(`winget install Microsoft.VCRedist.2015+.x64`). Veja o `install.md` para outros detalhes.

## Como usar

1. Coloque o(s) vídeo(s) numa pasta.
2. Abra o Claude Code **nessa pasta**.
3. Peça o que quer, por exemplo:
   - *"edita esse vídeo para Reels de até 1 minuto, tira as hesitações e coloca legenda"*
   - *"faz um corte de 30 segundos com a parte mais forte, legenda palavra por palavra"*
   - *"quero no mesmo estilo deste vídeo de referência: C:\...\referencia.mp4"*
4. Ele propõe um plano → você aprova → ele te mostra a prévia → você pede ajustes → `final.mp4`.

Tudo o que ele gera fica em `<sua pasta>/edit/` (transcrições, cortes, prévias, final). O vídeo original
nunca é alterado.

**Tempo (PC simples):** transcrição ≈ 1× a duração do vídeo; cada prévia de 1 min ≈ 2–4 min de render.

## Ferramentas incluídas

| Arquivo | O que faz |
|---|---|
| `helpers/transcribe.py`, `transcribe_batch.py` | Transcrição palavra por palavra (Whisper local; ElevenLabs opcional) |
| `helpers/pack_transcripts.py` | Junta as transcrições num texto compacto que o Claude lê |
| `helpers/timeline_view.py` | Miniaturas + forma de onda de um trecho |
| `helpers/render.py` | Corta, ajusta formato/zoom, trata o áudio, aplica sobreposições e legendas, normaliza volume |
| `helpers/face_track.py` | Detecta o rosto para nenhum texto tampá-lo |
| `helpers/sfx.py` | Gera efeitos sonoros (whoosh, pop, click, impacto, riser) |
| `helpers/grade.py` | Correção de cor |
| `helpers/extract_logo.py` | Recorta um logo de cor chapada de um vídeo de referência |
| `templates/captions_overlay.py` | Legenda palavra por palavra (estilo premium), com checagem de rosto |
| `templates/end_card.py` | Cartão final animado configurável |
| `references/short-form-playbook.md` | Manual de edição para vídeos curtos |

Exemplo direto (sem o Claude), gerando um cartão final:

```bash
.venv/Scripts/python templates/end_card.py -o endcard.mp4 --eyebrow "WORKSHOP DE EDIÇÃO" \
  --title "com Claude" --hero "22/10" --line "19H  •  AUDITÓRIO CENTRAL" --footer "inscrições no link da bio"
```

## Diferenças em relação ao video-use original

- Transcrição **local e gratuita** (faster-whisper) como padrão; ElevenLabs continua opcional.
- Correções para **Windows** (acentos/UTF-8, caminhos com `\` e acentos, fontes, Smart App Control).
- Formatos verticais, zoom por instante (sem corte de áudio), cadeia de tratamento de voz, efeitos sonoros
  sintetizados, detecção de rosto, modelos de legenda e cartão final, manual de edição pesquisado.

## Créditos e licenças

- Base: [browser-use/video-use](https://github.com/browser-use/video-use) — MIT (veja `LICENSE`).
- Fontes em `fonts/`: [Inter](https://github.com/rsms/inter) e [Montserrat](https://github.com/JulietaUla/Montserrat) —
  SIL Open Font License (`fonts/OFL-*.txt`).
- Transcrição: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT).

Use com responsabilidade: edite apenas vídeos que você tem direito de usar, e não use logos/marcas de terceiros
sem autorização.
