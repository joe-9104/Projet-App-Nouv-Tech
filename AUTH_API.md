# API d'authentification et isolation

## Authentification

Mécanisme retenu : session Django + cookie de session et jeton CSRF Django. Aucun mot de passe n'est retourné ou stocké en clair.

### POST `/api/auth/register/`
Public. Corps : `email`, `password`, optionnellement `first_name`/`last_name`. Réponse `201` : `{ "user": { "id", "email", "first_name", "last_name" } }`. Crée aussi la session.

### POST `/api/auth/login/`
Public. Corps : `email`, `password`. Réponse `200` : `{ "user": ... }`. Échec générique `401`.

### POST `/api/auth/logout/`
Authentifié. Invalide la session, réponse `200`.

### GET `/api/auth/me/`
Authentifié. Réponse `200` : `{ "user": ... }`.

### GET `/api/auth/csrf/`
Public. Retourne `csrfToken`. Les clients navigateur doivent l'envoyer dans `X-CSRFToken` pour les mutations de session.

### POST `/api/auth/google/`
Public. Corps : `{ "credential": "<Google_ID_token>" }`. Le jeton est vérifié par `google.oauth2.id_token.verify_oauth2_token` avec `GOOGLE_OAUTH_CLIENT_ID`. Seuls les tokens Google avec `email_verified=true` sont acceptés. Crée ou retrouve le compte par email vérifié; les comptes désactivés sont refusés.

## Documents et données privées

Tous les endpoints privés exigent une session valide. Les requêtes documentaires sont filtrées par `owner=request.user`. Un document étranger ou inexistant retourne `404` sans exposer son existence.

- `POST /api/documents/upload/` : PDF multipart `file`, propriétaire `request.user`.
- `GET /api/documents/` : documents du propriétaire uniquement.
- `GET /api/documents/<uuid>/` : détail du propriétaire uniquement.
- `GET /api/documents/<uuid>/file/` : téléchargement PDF du propriétaire uniquement.
- `GET /api/documents/<uuid>/assets/<uuid>` : figure du même document et du propriétaire uniquement.
- `POST /api/documents/<uuid>/index/` : indexation du document propriétaire uniquement.
- `POST /api/documents/search/` : corps `document_id`, `query`, `page_range`, `top_k`; autorise uniquement le document propriétaire.

## Google OAuth

Créez un OAuth 2.0 Client ID de type Web application dans Google Cloud. Autorisez les origines frontend nécessaires. Configurez `GOOGLE_OAUTH_CLIENT_ID`. Le secret OAuth n'est pas nécessaire si Google Identity Services fournit un ID token au backend. Ne jamais accepter un simple identifiant Google comme preuve ni envoyer un email choisi par le frontend.

Le véritable parcours avec Google n'a pas été exécuté sans identifiants Google réels. Les tests automatisés utilisent un double vérifiable du SDK Google.
