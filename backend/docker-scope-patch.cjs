const fs = require('fs');

const serverPath = '/app/dist/server.js';
let source = fs.readFileSync(serverPath, 'utf8');

function replaceOnce(expected, replacement) {
  if (source.split(expected).length !== 2) {
    throw new Error('Unexpected upstream source; refusing to apply the security patch');
  }
  source = source.replace(expected, replacement);
}

replaceOnce(
  'import { registerApiV4Tools } from "./api-v4-tools.js";',
  'import { registerApiV4Tools } from "./api-v4-tools.js";\nimport { registerComposeTools } from "./compose-tools.js";',
);

replaceOnce(
  '    if (config.allowMutations)\n        registerMutationTools(server, client, config);\n    if (config.allowMutations && config.allowDestructiveMutations) {\n        registerDestructiveTools(server, client);\n    }\n    registerApiV4Tools(server, client, readFacade, config);',
  `    if (config.allowMutations) {
        const register = server.registerTool.bind(server);
        server.registerTool = (name, ...args) => {
            if (name === "unraid_control_docker_container") return register(name, ...args);
            return undefined;
        };
        registerMutationTools(server, client, {...config, allowDestructiveMutations: true});
        server.registerTool = register;
    }
    registerComposeTools(server);
    registerApiV4Tools(server, client, readFacade, {...config, allowMutations: false, allowDestructiveMutations: false});`,
);
replaceOnce(
  'action: z.enum(["START", "STOP", "PAUSE", "UNPAUSE", "UPDATE"]),',
  'action: z.enum(["START", "STOP", "UPDATE"]),',
);
replaceOnce(
  'Start, stop, pause, unpause, or update one existing Docker container.',
  'Start, stop, or update one existing Docker container.',
);

fs.writeFileSync(serverPath, source);
console.log('Docker and allowlisted Compose mutation scope applied; confirmation gates retained.');
