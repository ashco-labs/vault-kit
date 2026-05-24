const path = require('path');
const home = require('os').homedir();

module.exports = {
  apps: [
    {
      name: 'vault-daemon',
      script: path.join(__dirname, '.venv', 'bin', 'python3'),
      args: `${path.join(__dirname, 'scripts', 'daemon.py')} ${path.join(home, 'ashco-vault')} --device-id mini`,
      autorestart: true,
      watch: false,
      env: {
        VAULT_DEVICE_ID: 'mini',
      },
    },
  ],
};
