const path = require('path');
const home = require('os').homedir();
const venv = path.join(__dirname, '.venv', 'bin', 'python3');
const scripts = path.join(__dirname, 'scripts');

module.exports = {
  apps: [
    {
      name: 'vault-indexer-cron',
      script: venv,
      args: `${path.join(scripts, 'indexer.py')} ${path.join(home, 'ashco-vault')}`,
      cron_restart: '*/10 * * * *',
      autorestart: false,
      watch: false,
    },
    {
      name: 'vault-auto-sweep',
      script: path.join(scripts, 'vault-commit.sh'),
      args: path.join(home, 'ashco-vault'),
      cron_restart: '0 * * * *',
      autorestart: false,
      watch: false,
    },
    {
      name: 'vault-chat-synth',
      script: venv,
      args: `${path.join(scripts, 'chat-synth.py')} --vault ${path.join(home, 'ashco-vault')} --device-id mini`,
      cron_restart: '*/30 * * * *',
      autorestart: false,
      watch: false,
    },
    {
      name: 'vault-indexer-watch',
      script: venv,
      args: `${path.join(scripts, 'indexer-watch.py')} ${path.join(home, 'ashco-vault')}`,
      autorestart: true,
      watch: false,
    },
  ],
};
