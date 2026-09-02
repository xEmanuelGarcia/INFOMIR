# MIR4 Telegram Companion

Sistema que observa a tela do MIR4 (sem interagir com o jogo, só lê pixels) e manda avisos
no Telegram quando: você morre, o vigor está acabando, uma missão do auto-play completa, um
objetivo da missão primária avança, ou periodicamente (status geral). Também responde `/status`
sob demanda com nível, poder, XP%, mapa atual, XP/min e cobre/min.

## Por que foi feito assim

**Não existe API oficial do MIR4.** A única forma de saber o que está acontecendo no jogo é
capturar a tela (`mss`) e ler o texto/cores com OCR (`Tesseract`/`pytesseract`). Isso define
praticamente todas as decisões de design abaixo.

**Não automatiza nenhum input no jogo.** O sistema só lê a tela e manda mensagens — nunca clica,
nunca aperta tecla. Automatizar ações no personagem (mesmo algo simples como apertar uma tecla
quando uma missão termina) seria jogar por você, o que viola os termos de uso do MIR4 (anti-cheat
ativo, bot proibido) e arrisca banimento. A linha que este projeto não cruza é essa: monitorar sim,
jogar não.

**Telegram em vez de WhatsApp.** O Telegram tem uma Bot API oficial, gratuita e simples de usar
(`@BotFather` + HTTP). O WhatsApp não tem API pessoal oficial — as alternativas são automação
não-oficial via navegador (frágil, quebra a cada atualização do WhatsApp) ou a API comercial da
Meta, que exige aprovação de número business. Não vale a pena para uso pessoal.

**Prints em JPEG, não PNG.** Um screenshot 1920x1080 em PNG fica em torno de 4-5MB; em JPEG
qualidade 85 fica por volta de 700KB (~6x menor). Em conexões mais lentas, os uploads de PNG
para o Telegram estavam estourando timeout e falhando silenciosamente. JPEG resolveu.

**Agendador de Tarefas do Windows, não um serviço de verdade.** Um Windows Service roda sem
sessão de usuário logada (como SYSTEM, na "Session 0"), e nesse modo a API de captura de tela do
Windows fica bloqueada — um serviço de verdade ficaria "cego". A solução foi usar o Agendador de
Tarefas com o gatilho "ao fazer logon" e "executar apenas com o usuário conectado": o processo
roda na sessão interativa (então a captura de tela funciona), sem depender de nenhum terminal
aberto (fechar o terminal ou apertar Ctrl+C não afeta nada), reinicia sozinho se cair, e volta a
rodar automaticamente no próximo login.

**Bastante camada de defesa contra ruído de OCR.** A fonte do HUD do jogo é pequena, estilizada,
e frequentemente coberta por efeitos de combate/partículas. Ler isso de forma confiável exigiu
várias camadas de proteção, construídas incrementalmente conforme os problemas apareciam em uso
real (não são otimizações prematuras — cada uma corrige um bug observado):

- **Localização dinâmica da barra de XP%**: a posição vertical do texto de XP muda dependendo de
  quantas mensagens (ganho de XP, cobre etc.) estão empilhadas acima dela naquele instante. Em vez
  de coordenadas fixas, o código procura a barra (uma faixa quase 100% de uma cor específica) numa
  janela maior e lê o texto logo acima dela.
- **Máscara de cor para texto de alto contraste** (XP%, vigor): isola o texto por cor antes do OCR
  em vez de tentar ler a imagem colorida direto, o que reduz bastante erro de leitura.
- **Limites de plausibilidade**: nível só é aceito entre 1-200, poder só é aceito se não variar
  mais de 50% do último valor bom conhecido, XP% só entre 0-100, vigor tem um teto e é comparado
  contra uma estimativa de decaimento (vigor só diminui com o tempo, nunca "pula" pra cima sem uma
  recarga real). Uma leitura implausível nunca é aceita como novo valor "confiável" — evita que um
  erro pontual de OCR (ex: nível lido como "772") contamine o resto do sistema, incluindo cálculos
  derivados como XP/minuto.
- **Cache do último valor bom conhecido**: se uma leitura falha (às vezes o próprio HUD não é
  desenhado em certas telas de morte, ex: algumas áreas PvP), a mensagem mostra o último valor
  válido em vez de "?".
- **Correção por similaridade para nomes de mapa**: OCR erra letras (`"Passagem"` vira `"cagum"`,
  por exemplo) mas o nome real do mapa deve ser sempre corrigido pro mesmo texto. Isso é feito
  comparando a leitura atual contra uma lista de mapas já confirmados e "corrigindo" quando a
  similaridade é alta o suficiente — mas com cuidado: andares diferentes do mesmo lugar (`1F` vs
  `2F` da Mina Abandonada) ou instâncias diferentes (`Sala I` vs `Sala II`) têm nomes quase
  idênticos por texto, então o número do andar e o sufixo em numeral romano são comparados à parte
  e precisam bater exatamente — senão dois lugares diferentes de verdade seriam tratados como o
  mesmo mapa.
- **Confirmação por leitura repetida**: um mapa (ou objetivo de missão) desconhecido só é aceito
  como "novo" depois de aparecer parecido em 2-3 leituras seguidas — ruído aleatório de OCR
  raramente se repete do mesmo jeito duas vezes, um mapa novo de verdade sim.
- **Estado de alerta persistido em disco**: se o script precisar reiniciar (crash, eu debugando,
  reboot do PC), ele lembra se um alerta já foi disparado, então não manda a mesma notificação de
  novo só porque o processo reiniciou no meio de uma morte/vigor baixo/etc.
- **Detecção por cor além de texto**: pra saber quando um objetivo da missão primária termina, ler
  o texto tremido é frágil — em vez disso, o ícone da missão tem uma borda azul brilhante enquanto
  o objetivo está em andamento, que some quando ele completa. Detectar isso é uma simples contagem
  de pixels de uma cor específica, bem mais confiável que OCR de texto pequeno.

## Estrutura

| Arquivo | O que faz |
|---|---|
| `common.py` | Toda a lógica compartilhada: captura, OCR, extração de stats, envio pro Telegram, e as máquinas de estado de cada tipo de alerta (morte, vigor, mapa, missão, cobre/min, XP/min). |
| `watcher.py` | Loop principal. A cada ~1.5s: checa morte, vigor, mapa, cobre, missão do auto-play, objetivo da missão primária; a cada 30min manda um relatório periódico. |
| `telegram_listener.py` | Fica ouvindo mensagens no bot (long polling) — responde `/status` com print + stats atuais. |
| `calibrate.py` | Ferramenta interativa: você aperta ENTER com a tela de morte visível, seleciona a área na imagem, e ele salva o template de referência + a região de busca em `config.json`. |
| `snapshot.py` | Só tira print da tela inteira continuamente pra um arquivo (`snapshot.png`) — usado pra inspeção/debug ao vivo, não faz parte do fluxo de alertas. |
| `analyze_samples.py` | Ferramenta de regressão: roda a extração de stats contra todos os prints salvos (histórico de evidências + snapshots de eventos) de uma vez, pra achar onde a leitura ainda falha. |
| `launcher.py` | Janela (tkinter) com Play/Pause pras tarefas agendadas, atalho pra calibração e visualização do log. |

## Como funciona por dentro

1. **Detecção de morte**: `calibrate.py` grava um recorte da tela (o ícone/botão de ressuscitar)
   como template. Em tempo real, `watcher.py` compara continuamente a região configurada contra
   esse template (`cv2.matchTemplate`); acima de um threshold, é considerado "morto"; abaixo de um
   threshold menor (histerese), "vivo" de novo — evita ficar alternando por ruído perto da borda.
2. **Vigor, mapa, nível/poder/XP%**: recortes fixos (calibrados manualmente olhando a tela real,
   ver coordenadas em `common.py`) + Tesseract, com as camadas de defesa listadas acima.
3. **Cobre/min e XP/min**: cada leitura boa é comparada com a última salva (com timestamp);
   a diferença dividida pelo tempo decorrido dá a taxa. O acumulador de cobre soma qualquer
   `"Cobre +N"` visto no feed de mensagens desde a última leitura, evitando contar a mesma
   mensagem duas vezes.
4. **Notificações**: cada tipo de alerta (morte, vigor baixo, missão do auto-play concluída,
   objetivo da missão primária concluído) tem uma flag "já avisei" persistida em `*_state.json`,
   que só reseta quando a condição volta ao normal (ex: vigor sobe de novo, character ressuscita).

## Configuração

**Testado com:** Python 3.13.5, Tesseract 5.5.0. As versões das bibliotecas Python estão fixadas
em `requirements.txt`.

1. Instale as dependências: `pip install -r requirements.txt`
2. Instale o [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (Windows) e ajuste
   `TESSERACT_PATH` em `common.py` se o caminho de instalação for diferente.
3. Copie `.env.example` para `.env` e preencha com o token do seu bot (crie um com
   [@BotFather](https://t.me/BotFather)) e o seu `chat_id` (mande uma mensagem pro bot e consulte
   `https://api.telegram.org/bot<TOKEN>/getUpdates`).
4. Copie `config.json.example` para `config.json` (os valores de `region` são específicos da sua
   resolução/posição de tela — serão sobrescritos pela calibração).
5. Com o jogo aberto em modo janela/borderless (não tela cheia exclusiva) e a tela de morte
   visível, rode `python calibrate.py`.
6. Rode `python watcher.py` e `python telegram_listener.py` (em terminais separados, ou como
   tarefas agendadas — veja abaixo).

### Rodar sem depender de terminal aberto (Windows Task Scheduler)

```powershell
$pythonw = "CAMINHO\PARA\pythonw.exe"
$workdir = "CAMINHO\PARA\ESTE\PROJETO"
$user = "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user

foreach ($pair in @{"MIR4Watcher"="watcher.py"; "MIR4TelegramListener"="telegram_listener.py"}.GetEnumerator()) {
    $action = New-ScheduledTaskAction -Execute $pythonw -Argument $pair.Value -WorkingDirectory $workdir
    Register-ScheduledTask -TaskName $pair.Key -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
}
```

Depois: `Start-ScheduledTask -TaskName "MIR4Watcher"` (e o mesmo pro listener). Pra parar:
`Stop-ScheduledTask`.

## Limitações conhecidas

- Algumas telas de morte (certas áreas PvP/raid) não desenham o HUD principal — nesses casos
  nível/poder/XP% caem no fallback do último valor conhecido em vez de mostrar o valor daquele
  instante exato.
- OCR de dígito único (o número do andar em `[6F]`, por exemplo) ocasionalmente falha em frames
  com muito efeito visual de combate — o sistema de confirmação por repetição filtra a maioria
  dos casos, mas leituras isoladas malformadas podem aparecer no histórico interno até se
  autocorrigirem na leitura seguinte.
- Calibração (`config.json`, `templates/`) é específica da resolução e posição da janela do jogo
  na sua tela — não é portável entre máquinas/monitores diferentes sem recalibrar.
