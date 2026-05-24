module.exports = {
  apps: [
    {
      name: 'vault-indexer-cron',
      script: '/Users/alpha/repos/vault-kit/.venv/bin/python3',
      args: '/Users/alpha/repos/vault-kit/scripts/indexer.py /Users/alpha/ashco-vault',
      cron_restart: '*/10 * * * *',
      autorestart: false,
      watch: false,
      cwd: '/Users/alpha/repos/vault-kit'
    },
    {
      name: 'vault-auto-sweep',
      script: '/Users/alpha/repos/vault-kit/scripts/vault-commit.sh',
      args: '/Users/alpha/ashco-vault',
      cron_restart: '0 * * * *',
      autorestart: false,
      watch: false,
      cwd: '/Users/alpha/repos/vault-kit'
    }
  ]
};
