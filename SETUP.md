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
