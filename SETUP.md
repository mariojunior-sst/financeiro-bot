# Bot Financeiro — Guia de Configuração

Tempo estimado: 20 a 30 minutos (feito uma vez só).

---

## O que você vai precisar

- Conta Google (Gmail)
- Conta no Telegram
- Conta no Railway (gratuita) — railway.app

---

## Passo 1 — Criar o bot no Telegram

1. Abra o Telegram e pesquise por **@BotFather**
2. Envie o comando `/newbot`
3. Dê um nome pro bot (ex: `Financeiro Mario`)
4. Dê um nome de usuário pro bot — precisa terminar em `bot` (ex: `financeiro_mario_bot`)
5. O BotFather vai te enviar um **token** parecido com:
   ```
   7412345678:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
6. Salve esse token — você vai precisar dele no Passo 4.

---

## Passo 2 — Descobrir seu ID no Telegram

1. No Telegram, pesquise por **@userinfobot**
2. Envie qualquer mensagem pra ele
3. Ele vai responder com seu **Id** numérico (ex: `123456789`)
4. Salve esse número — ele vai garantir que só você pode usar o bot.

---

## Passo 3 — Criar a planilha no Google Sheets

1. Acesse [sheets.google.com](https://sheets.google.com) e crie uma planilha nova
2. Dê o nome: **Financeiro**
3. Anote o **ID da planilha** — ele fica na URL:
   ```
   https://docs.google.com/spreadsheets/d/ESTE_É_O_ID/edit
   ```

---

## Passo 4 — Configurar a API do Google (conta de serviço)

Esse passo permite que o bot escreva na sua planilha automaticamente.

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Crie um projeto novo (ex: `bot-financeiro`)
3. No menu lateral, vá em **APIs e serviços → Biblioteca**
4. Pesquise **Google Sheets API** e clique em **Ativar**
5. Pesquise **Google Drive API** e clique em **Ativar**
6. Vá em **APIs e serviços → Credenciais**
7. Clique em **Criar credenciais → Conta de serviço**
8. Nome: `bot-financeiro` → clique em **Criar e continuar** → **Concluído**
9. Na lista de contas de serviço, clique na que você criou
10. Vá na aba **Chaves** → **Adicionar chave → Criar nova chave → JSON**
11. Um arquivo `.json` será baixado — guarde bem esse arquivo

**Compartilhar a planilha com a conta de serviço:**
1. Abra o arquivo JSON baixado e copie o valor de `"client_email"` (algo como `bot-financeiro@projeto.iam.gserviceaccount.com`)
2. Abra sua planilha no Google Sheets
3. Clique em **Compartilhar** (canto superior direito)
4. Cole o `client_email` e dê permissão de **Editor**
5. Clique em **Enviar**

---

## Passo 5 — Fazer o deploy no Railway

1. Acesse [railway.app](https://railway.app) e crie uma conta (pode usar o Google)
2. Clique em **New Project → Deploy from GitHub repo**
3. Conecte sua conta do GitHub e faça upload desta pasta (`financeiro-bot`) para um repositório
   > Se não tiver GitHub: clique em **New Project → Empty project**, depois **+ Add service → GitHub Repo** e siga as instruções para conectar.
4. Após conectar o repositório, o Railway vai detectar o `Procfile` automaticamente

**Configurar as variáveis de ambiente no Railway:**

Vá em **Settings → Variables** e adicione:

| Variável | Valor |
|---|---|
| `TELEGRAM_TOKEN` | Token gerado pelo BotFather |
| `ALLOWED_USER_ID` | Seu ID do Telegram (do @userinfobot) |
| `SHEET_ID` | ID da sua planilha do Google Sheets |
| `GOOGLE_CREDENTIALS` | Conteúdo completo do arquivo JSON (copie e cole tudo) |

> Para o `GOOGLE_CREDENTIALS`: abra o arquivo JSON no Bloco de Notas, selecione tudo (Ctrl+A), copie e cole no campo do Railway.

5. Clique em **Deploy** — o Railway vai instalar as dependências e iniciar o bot.

---

## Passo 6 — Testar

1. Abra o Telegram e pesquise pelo nome do seu bot (ex: `@financeiro_mario_bot`)
2. Envie `/start`
3. O bot deve responder com as instruções
4. Teste um lançamento:
   ```
   receita 1500 extinprag manutenção extintores cliente teste
   ```
5. Verifique se apareceu na planilha do Google Sheets (aba **Lançamentos**)

---

## Como usar no dia a dia

**Registrar lançamento:**
```
receita 1500 extinprag manutenção extintores cliente X
custo 200 extinprag compra de materiais
receita 3000 vsafety consultoria NR12 cliente Y
custo 150 pessoal supermercado
```

**Ver resumo do mês:**
```
/resumo
```

**Ver últimos lançamentos:**
```
/historico
```

---

## Dúvidas frequentes

**O bot não responde:**
- Verifique se o `TELEGRAM_TOKEN` está correto no Railway
- Veja os logs no Railway (aba **Logs**)

**Erro ao salvar na planilha:**
- Confirme que o `client_email` foi adicionado como editor na planilha
- Verifique se o `SHEET_ID` está correto

**Quero ver o relatório em mais detalhes:**
- Acesse a planilha diretamente — todos os lançamentos ficam na aba **Lançamentos**
- Você pode criar filtros, gráficos e tabelas dinâmicas diretamente no Sheets


---

## Contas fixas e lembrete de pagamento

O bot avisa sozinho, no Telegram, sobre as contas fixas mensais — para não
repetir o esquecimento que gera juros.

### Duas ideias que definem o módulo

**1. Conta fixa é fixa no compromisso, não no valor.** Energia, financiamento e
telefone mudam todo mês, então o valor **não é cadastrado**. O que se cadastra é
o que vence e em que dia.

**2. Não existe comando de "paguei".** Quando você lança o custo — do jeito que
já lançava — o bot reconhece a conta pela descrição e **dá a baixa sozinho**,
gravando o valor real daquele mês. Um passo manual a mais seria mais uma coisa
para esquecer, que é exatamente o problema que o módulo resolve.

### Como funciona

1. Cadastra a conta uma vez:
   `/novaconta Financiamento da casa | 10 | pessoal`
   (nome | dia do vencimento | empresa | categoria opcional)
2. Todo dia às **07:00 (horário de Belém)** o bot verifica o que está em aberto.
3. Ele **só escreve quando há algo a cobrar** — atrasada, vencendo hoje, ou
   vencendo nos próximos 5 dias. Silêncio significa que está tudo em dia.
4. No **dia 1º** ele manda a agenda do mês inteiro, antes de qualquer cobrança.
5. Você paga e lança o custo como sempre:
   `custo 2410,55 pessoal financiamento da casa`
   → o custo entra no financeiro **e** a conta é quitada, numa tacada só.

### Como o bot reconhece a conta no custo lançado

Compara as palavras do nome cadastrado com as da descrição do lançamento,
ignorando conectivos (`de`, `da`, `conta`, `boleto`…). Aceita quando o nome
inteiro aparece, ou quando aparece metade dele **com pelo menos uma palavra
distintiva** (5+ letras).

Na prática: `financiamento` quita "Financiamento da casa"; `casa de carnes`
não. O custo também precisa ser da **mesma empresa** da conta.

Se duas contas empatarem (`energia` com "Energia casa" e "Energia escritório"
cadastradas), ele **pergunta em vez de chutar** — dar baixa na conta errada é
pior do que perguntar.

### Comandos

| Comando | O que faz |
|---|---|
| `/novaconta nome \| dia \| empresa` | Cadastra uma conta fixa |
| `/contas` | Todas as contas, urgente primeiro |
| `/lembrete` | Mostra agora o mesmo texto do aviso automático |
| `/pausarconta` | Pausa ou retoma uma conta (contrato encerrado, etc.) |
| `/paguei` | Baixa manual — **só** para conta paga fora do bot |

`/paguei` existe para o caso de débito automático ou pagamento feito no banco
sem lançar o custo. Ele não lança nada no financeiro, só tira a conta do radar.

### Aba `Contas Fixas` (criada sozinha na primeira execução)

| Coluna | Conteúdo |
|---|---|
| Nome | Identificação da conta — é por ela que o casamento acontece |
| Dia | Dia do vencimento (1 a 31) |
| Empresa | EXTINPRAG, VSAFETY ou PESSOAL |
| Categoria | Categoria de gasto |
| Ativa | SIM / NÃO (o `/pausarconta` mexe aqui) |
| Pago Até | Última competência quitada, no formato `AAAA-MM` |
| Último Valor | Preenchido pelo bot na baixa — referência, não previsão |
| Observação | Livre |

**`Pago Até` é o coração do controle.** Se ele marca `2026-07` e já estamos em
setembro, o bot entende que **agosto ficou em aberto** e cobra o mês esquecido —
mesmo com o mês já virado. Cada baixa quita **um** mês, começando sempre pelo
mais antigo, e o bot avisa quantos ainda restam. Assim pagar setembro não
apaga o atraso de agosto por tabela.

Dia 29, 30 ou 31 cai automaticamente no último dia dos meses mais curtos.

**Cuidado ao editar `Pago Até` na mão:** digitando `2026-08`, o Sheets converte
para data. A leitura aguenta (converte de volta), mas o formato texto é o
esperado.

### Variáveis de ambiente (opcionais, no serviço `worker`)

| Variável | Padrão | Para quê |
|---|---|---|
| `HORA_LEMBRETE` | `07:00` | Horário do aviso diário |
| `ANTECEDENCIA_AVISO` | `5` | Dias de antecedência do aviso |
| `FUSO_HORARIO` | `America/Belem` | Fuso do agendamento |

O aviso é enviado para o `ALLOWED_USER_ID` — a mesma variável que já autoriza o
uso do bot, então não há nada novo a configurar para receber os lembretes.

**Atenção na dependência:** o lembrete depende de
`python-telegram-bot[job-queue]` (o extra instala o APScheduler). Sem o extra o
bot sobe e os comandos funcionam, mas o aviso automático não roda — e o log
avisa isso na inicialização.
