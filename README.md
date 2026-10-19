# Unraid MCP sécurisé

Ce dépôt construit deux images complémentaires pour connecter ChatGPT, Codex ou une autre application compatible MCP à un serveur Unraid.

| Image | Rôle |
| --- | --- |
| `ghcr.io/maxhugit/unraid-mcp:latest` | Interroge l’API officielle Unraid. Les écritures sont limitées au démarrage, à l’arrêt et à la mise à jour des conteneurs. |
| `ghcr.io/maxhugit/unraid-mcp-oauth:latest` | Protège l’accès public avec OAuth/OpenID Connect et transmet les requêtes authentifiées au serveur MCP interne. |

La passerelle OAuth est la seule entrée à publier derrière le reverse proxy. Le serveur principal écoute uniquement sur l’adresse locale d’Unraid.

## Protections intégrées

- images exécutées sans privilèges et avec un système de fichiers en lecture seule ;
- suppression de toutes les capacités Linux et activation de `no-new-privileges` ;
- aucune clé, aucun certificat et aucun mot de passe inclus dans les images ;
- accès au serveur MCP interne protégé par un jeton distinct ;
- commandes d’écriture limitées à `START`, `STOP` et `UPDATE` ;
- confirmation explicite exigée par l’outil MCP avant une mise à jour ;
- OAuth obligatoire sur l’URL publique.

## 1. Préparer Unraid

Créez le dossier de configuration depuis un terminal Unraid :

```bash
mkdir -p /mnt/user/appdata/unraid-mcp/oauth-state
chmod 700 /mnt/user/appdata/unraid-mcp /mnt/user/appdata/unraid-mcp/oauth-state
```

Copiez ensuite les deux exemples du dossier `config` :

```bash
cp config/backend.env.example /mnt/user/appdata/unraid-mcp/backend.env
cp config/gateway.json.example /mnt/user/appdata/unraid-mcp/gateway.json
chmod 600 /mnt/user/appdata/unraid-mcp/backend.env /mnt/user/appdata/unraid-mcp/gateway.json
```

Si le dépôt n’est pas cloné sur Unraid, téléchargez les exemples depuis GitHub ou créez les fichiers manuellement à partir de leur contenu.

## 2. Créer les identifiants

### Clé API Unraid

Créez une clé API dédiée dans Unraid. Accordez uniquement les permissions de consultation nécessaires et la permission Docker de mise à jour. N’utilisez pas une clé administrateur générale.

### Jetons locaux

Générez deux valeurs aléatoires différentes :

```bash
openssl rand -hex 32
openssl rand -hex 32
```

- placez la première dans `MCP_AUTH_TOKEN` et dans `backend_token` ;
- placez la seconde dans `signing_key`.

## 3. Configurer le serveur MCP

Éditez `/mnt/user/appdata/unraid-mcp/backend.env` :

- `UNRAID_URL` : URL locale de l’API GraphQL Unraid ;
- `UNRAID_API_KEY` : clé API dédiée ;
- `MCP_HOST=127.0.0.1` : empêche une exposition directe sur le réseau ;
- `MCP_PORT=8310` : port interne utilisé par la passerelle ;
- `MCP_AUTH_TOKEN` : premier jeton aléatoire.

Conservez `UNRAID_ALLOW_DESTRUCTIVE_MUTATIONS=false`. L’image applique séparément une liste blanche stricte pour la commande Docker autorisée.

## 4. Configurer OAuth

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

## 5. Installer les formulaires DockerMan

Copiez les deux modèles dans Unraid :

```bash
cp templates/my-unraid-mcp.xml /boot/config/plugins/dockerMan/templates-user/
cp templates/my-unraid-mcp-oauth.xml /boot/config/plugins/dockerMan/templates-user/
```

Dans l’interface Unraid, ouvrez **Docker**, puis **Ajouter un conteneur** et choisissez successivement :

1. `unraid-mcp` ;
2. `unraid-mcp-oauth`.

Vérifiez les chemins `appdata` dans les formulaires si votre stockage n’utilise pas `/mnt/user/appdata`.

## 6. Configurer le reverse proxy

Publiez uniquement le port `8311` de la passerelle OAuth derrière HTTPS. Ne publiez jamais le port `8310` du serveur principal.

La route publique doit pointer vers :

```text
http://ADRESSE_UNRAID:8311
```

## 7. Vérifier l’installation

Les deux conteneurs doivent être actifs et `unraid-mcp` doit être sain. Un appel anonyme vers l’URL MCP publique doit être refusé avec un code HTTP `401`.

Après authentification, vérifiez d’abord les outils de lecture et les journaux. Testez ensuite `START` et `STOP` sur un conteneur sans importance. Une opération `UPDATE` doit demander une confirmation explicite.

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
oauth/         passerelle OAuth FastMCP
config/        exemples sans secrets
templates/     formulaires DockerMan pour Unraid
.github/       publication automatique vers GHCR
```

## Crédits

Le serveur principal repose sur le projet communautaire `lemanjo/unraid-mcp`. La passerelle utilise FastMCP.
