# Unraid MCP sécurisé

Ce dépôt construit trois images complémentaires pour connecter ChatGPT, Codex ou une autre application compatible MCP à un serveur Unraid.

| Image | Rôle |
| --- | --- |
| `ghcr.io/maxhugit/unraid-mcp:latest` | Interroge l’API officielle Unraid. Les écritures sont limitées au démarrage, à l’arrêt et à la mise à jour des conteneurs. |
| `ghcr.io/maxhugit/unraid-mcp-oauth:latest` | Protège l’accès public avec OAuth/OpenID Connect et transmet les requêtes authentifiées au serveur MCP interne. |
| `ghcr.io/maxhugit/unraid-compose-agent:latest` | Met à jour uniquement les stacks Compose, fichiers d’environnement et dépôts d’images déclarés dans une liste blanche locale. |

La passerelle OAuth est la seule entrée à publier derrière le reverse proxy. Le serveur principal écoute uniquement sur l’adresse locale d’Unraid.

## Protections intégrées

- images exécutées sans privilèges et avec un système de fichiers en lecture seule ;
- suppression de toutes les capacités Linux et activation de `no-new-privileges` ;
- aucune clé, aucun certificat et aucun mot de passe inclus dans les images ;
- accès au serveur MCP interne protégé par un jeton distinct ;
- commandes d’écriture limitées à `START`, `STOP` et `UPDATE` ;
- confirmation explicite exigée par l’outil MCP avant une mise à jour ;
- agent Compose lié à `127.0.0.1`, protégé par un jeton distinct et sans endpoint de commande arbitraire ;
- images Compose limitées à des tags immuables `sha-*` et à un dépôt fixé par stack ;
- restauration automatique de l’ancien fichier d’environnement si la recréation échoue ;
- OAuth obligatoire sur l’URL publique.

L’agent Compose monte le socket Docker, ce qui lui donne techniquement un pouvoir élevé sur l’hôte. Il est donc isolé du réseau public et n’accepte qu’une opération codée en dur sur des chemins explicitement autorisés. Ne publiez jamais son port `8320`.

## 1. Préparer Unraid

Créez le dossier de configuration depuis un terminal Unraid :

```bash
mkdir -p /mnt/user/appdata/unraid-mcp/oauth-state
chmod 700 /mnt/user/appdata/unraid-mcp /mnt/user/appdata/unraid-mcp/oauth-state
```

Copiez ensuite les exemples du dossier `config` :

```bash
cp config/backend.env.example /mnt/user/appdata/unraid-mcp/backend.env
cp config/gateway.json.example /mnt/user/appdata/unraid-mcp/gateway.json
cp config/compose-agent.env.example /mnt/user/appdata/unraid-mcp/compose-agent.env
cp config/compose-stacks.json.example /mnt/user/appdata/unraid-mcp/compose-stacks.json
chmod 600 /mnt/user/appdata/unraid-mcp/backend.env /mnt/user/appdata/unraid-mcp/gateway.json /mnt/user/appdata/unraid-mcp/compose-agent.env /mnt/user/appdata/unraid-mcp/compose-stacks.json
```

Si le dépôt n’est pas cloné sur Unraid, téléchargez les exemples depuis GitHub ou créez les fichiers manuellement à partir de leur contenu.

## 2. Créer les identifiants

### Clé API Unraid

Créez une clé API dédiée dans Unraid. Accordez uniquement les permissions de consultation nécessaires et la permission Docker de mise à jour. N’utilisez pas une clé administrateur générale.

### Jetons locaux

Générez trois valeurs aléatoires différentes :

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
```

- placez la première dans `MCP_AUTH_TOKEN` et dans `backend_token` ;
- placez la seconde dans `signing_key`.
- placez la troisième dans `MCP_COMPOSE_AGENT_TOKEN` et `COMPOSE_AGENT_TOKEN`.

## 3. Configurer le serveur MCP

Éditez `/mnt/user/appdata/unraid-mcp/backend.env` :

- `UNRAID_URL` : URL locale de l’API GraphQL Unraid ;
- `UNRAID_API_KEY` : clé API dédiée ;
- `MCP_HOST=127.0.0.1` : empêche une exposition directe sur le réseau ;
- `MCP_PORT=8310` : port interne utilisé par la passerelle ;
- `MCP_AUTH_TOKEN` : premier jeton aléatoire.
- `MCP_COMPOSE_AGENT_URL=http://127.0.0.1:8320` : agent Compose local ;
- `MCP_COMPOSE_AGENT_TOKEN` : troisième jeton aléatoire.

Conservez `UNRAID_ALLOW_DESTRUCTIVE_MUTATIONS=false`. L’image applique séparément une liste blanche stricte pour les commandes Docker autorisées.

## 4. Configurer les stacks Compose autorisées

Éditez `/mnt/user/appdata/unraid-mcp/compose-agent.env` et placez le troisième jeton dans `COMPOSE_AGENT_TOKEN`.

Éditez ensuite `/mnt/user/appdata/unraid-mcp/compose-stacks.json`. Chaque entrée fixe :

- le nom logique accepté par l’outil MCP ;
- le dossier monté dans l’agent ;
- les noms exacts du fichier Compose et du fichier d’environnement ;
- l’unique variable d’image modifiable ;
- l’unique dépôt d’image autorisé ;
- le nom de projet Compose.

La configuration fournie autorise uniquement `codex-web`, `CODEX_APP_IMAGE` et `ghcr.io/maxhugit/codex-webui-unraid`. L’outil refuse `latest`, les autres dépôts, les chemins libres et les liens symboliques.

## 5. Configurer OAuth

Créez une application OpenID Connect chez Authentik ou un fournisseur équivalent. Déclarez l’URL publique de la passerelle et les URL de retour des clients utilisés.

Éditez `/mnt/user/appdata/unraid-mcp/gateway.json` :

- `discovery_url` : document de découverte OpenID Connect ;
- `client_id` et `client_secret` : identifiants de l’application OAuth ;
- `base_url` : URL HTTPS publique de la passerelle MCP ;
- `allowed_client_redirect_uris` : liste blanche des retours ChatGPT, Codex et Codex WebUI ;
- `backend_url=http://127.0.0.1:8310/mcp` ;
- `listen_host=0.0.0.0` et `listen_port=8311` ;
- `backend_token` : même valeur que `MCP_AUTH_TOKEN` ;
- `signing_key` : second secret aléatoire.

Le fichier contient des secrets : ne le commitez jamais et ne le placez jamais dans une image.

## 6. Installer les formulaires DockerMan

Copiez les trois modèles dans Unraid :

```bash
cp templates/my-unraid-mcp.xml /boot/config/plugins/dockerMan/templates-user/
cp templates/my-unraid-mcp-oauth.xml /boot/config/plugins/dockerMan/templates-user/
cp templates/my-unraid-compose-agent.xml /boot/config/plugins/dockerMan/templates-user/
```

Dans l’interface Unraid, ouvrez **Docker**, puis **Ajouter un conteneur** et choisissez successivement :

1. `unraid-compose-agent` ;
2. `unraid-mcp` ;
3. `unraid-mcp-oauth`.

Vérifiez particulièrement que le montage `/stacks/codex-web` pointe vers le dossier réel de la stack, par défaut `/mnt/pool/appdata/codex-web`. Vérifiez également les chemins `appdata` si votre stockage n’utilise pas `/mnt/user/appdata`.

## 7. Configurer le reverse proxy

Publiez uniquement le port `8311` de la passerelle OAuth derrière HTTPS. Ne publiez jamais les ports `8310` du serveur principal ou `8320` de l’agent Compose.

La route publique doit pointer vers :

```text
http://ADRESSE_UNRAID:8311
```

## 8. Vérifier l’installation

Les trois conteneurs doivent être actifs et `unraid-mcp` ainsi que `unraid-compose-agent` doivent être sains. Un appel anonyme vers l’URL MCP publique doit être refusé avec un code HTTP `401`.

Après authentification, vérifiez d’abord les outils de lecture et les journaux. `unraid_list_compose_stacks` doit retourner `codex-web` sans révéler les chemins de l’hôte. Testez ensuite `START` et `STOP` sur un conteneur sans importance. Les opérations `UPDATE` et `unraid_update_compose_stack` doivent demander une confirmation explicite.

Exemple de mise à jour autorisée :

```text
stack=codex-web
image=ghcr.io/maxhugit/codex-webui-unraid:sha-b481c72
confirmation=UPDATE_COMPOSE_STACK
```

## Mises à jour

Chaque modification de `main` construit et publie automatiquement :

- un tag `latest` ;
- un tag immuable `sha-<commit>`.

Unraid peut détecter une nouvelle image grâce à GHCR. Utilisez le bouton de mise à jour du conteneur ou forcez la récupération de l’image avant de réappliquer le formulaire.

## Retour arrière

Avant une mise à jour importante, relevez le tag `sha-...` actuellement utilisé. Pour revenir en arrière, remplacez temporairement `latest` par ce tag immuable dans le champ **Repository** du formulaire Unraid, puis réappliquez le conteneur. Les données OAuth et les fichiers de configuration restent dans `appdata` et ne sont pas supprimés.

## Arborescence

```text
backend/       image MCP et restriction des commandes Docker
compose-agent/ agent local avec accès restreint à Docker Compose
oauth/         passerelle OAuth FastMCP
config/        exemples sans secrets
templates/     formulaires DockerMan pour Unraid
.github/       publication automatique vers GHCR
```

## Crédits

Le serveur principal repose sur le projet communautaire `lemanjo/unraid-mcp`. La passerelle utilise FastMCP.
