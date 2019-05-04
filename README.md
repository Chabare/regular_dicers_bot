# regular_dicers_bot

The shitpost of telegram bots.

Reminds people to drink cocktails on a regular basis.

```text
                       _                  _ _                     _           _
  _ __ ___  __ _ _   _| | __ _ _ __    __| (_) ___ ___ _ __ ___  | |__   ___ | |_
 | '__/ _ \/ _` | | | | |/ _` | '__|  / _` | |/ __/ _ \ '__/ __| | '_ \ / _ \| __|
 | | |  __/ (_| | |_| | | (_| | |    | (_| | | (_|  __/ |  \__ \ | |_) | (_) | |_
 |_|  \___|\__, |\__,_|_|\__,_|_|     \__,_|_|\___\___|_|  |___/ |_.__/ \___/ \__|
           |___/
```

## Configuration

Create the `secrets.json` file:

`mv secrets.json.example secrets.json`

### Required

#### API Token

Get your API from [Botfather](https://web.telegram.org/#/im?p=@BotFather).
Put it in the `secrets.json` file (key: `token`).

### Optional

#### Google calendar

_TODO_ Wait for [Issue #25](#25) to document this.

#### Sentry

If you want to enable sentry, get your token from
`https://sentry.io/settings/{{your organization}}/projects/{{your project}}/keys/`.
Put your sentry_dsn in `secrets.json` file (key: `sentry_dsn`)

### Telegram

#### Commands

You can copy and paste the contents from `commands.md` to botfather to register the commands.

#### Group privacy

This settings should be disabled if you want the spam detection to work.

## Installation

This project needs python3.7

### Virtualenv

```bash
git clone git@github.com:OpenAlcoholics/regular_dicers_bot.git
virtualenv .venv
.venv/bin/activate
pip install -r requirements.txt
python -O -B
```

### docker-compose

```bash
docker-compose build
docker-compose up -d
## Tail the logs
docker-compose logs -f
```

## Generate documentation

```bash
pdoc --html dicers_bot
```

### View

```bash
{browser} html/dicers_bot/index.html
```
