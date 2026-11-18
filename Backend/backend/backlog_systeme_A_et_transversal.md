# Backlog de référence — Système A et tickets transversaux

> **Projet :** plateforme d'apprentissage personnalisée basée sur un LLM et RAG  
> **Périmètre :** tickets du développeur du système A (Document / RAG) et tickets transversaux uniquement.  
> **Source :** backlog de référence établi par l'équipe. Les titres, descriptions, priorités, estimations et dépendances ci-dessous reprennent les informations disponibles.

## 1. Contexte général

Le backend est un **monolithe Django** organisé en applications/modules logiques. A, B et C ne sont pas des serveurs indépendants.

- **Système A — Document / RAG :** import et traitement documentaire, préservation des figures, découpage, indexation et recherche documentaire.
- **Système B — Génération / évaluation pédagogique :** génération de contenus d'apprentissage et évaluations.
- **Système C — Modèle apprenant / recommandations :** suivi des connaissances de l'apprenant et recommandations.
- **UI — Interface utilisateur :** client de la plateforme.
- **Transversal :** contrats partagés, authentification, intégration et livraison.

Les tickets B, C et UI ne sont pas détaillés ici : ce document sert de référence au développeur du système A et aux agents IA qui l'assistent.

**Légende :** P0 = priorité structurante ; P1 = priorité fonctionnelle. Les estimations sont exprimées en points. Les dépendances désignent les tickets dont la réalisation ou les décisions sont nécessaires ; elles ne signifient pas toujours que le développement indépendant doit rester bloqué.

## 2. Tickets du système A — Document / RAG

Le système A comprend **8 tickets**, pour un total de **27 points**.

| ID | Titre | Description du backlog | Priorité | Estimation | Dépendances |
|---|---|---|---|---:|---|
| DOC-01 | Import PDF et cycle de vie | Validation du fichier, document privé et états `pending`, `processing`, `ready`, `error`. | P1 | 3 | AUTH-02, ARC-02 |
| DOC-02 | Extraction et normalisation | MinerU et adaptateur normalisant le résultat vers le schéma interne ; texte structuré, références et erreurs. | P1 | 5 | DOC-01, ARC-02 |
| DOC-03 | Liste des documents et de leur état | L'utilisateur consulte ses propres documents et leur progression de traitement. | P1 | 2 | DOC-01, AUTH-02 |
| VIS-01 | Préservation des figures et métadonnées | Références stables, document source et page d'origine. | P1 | 3 | DOC-02, ARC-02 |
| VIS-02 | Association des figures aux passages | Relations entre les passages et les figures, avec indication de l'incertitude. | P1 | 3 | VIS-01, ARC-02 |
| RAG-01 | Découpage structure-first | Création des passages à partir du contenu normalisé, avec provenance et références stables. | P1 | 3 | DOC-02, ARC-02 |
| RAG-02 | Indexation des passages et métadonnées | Mise en place d'un index permettant de retrouver les passages. | P1 | 3 | RAG-01, ARC-02 |
| RAG-03 | Service de recherche documentaire | Récupération selon le périmètre, références sources, figures associées et résultats explicitement vides ou insuffisants. | P1 | 5 | RAG-02, VIS-02, ARC-02, ARC-04 |

### État d'avancement connu

- **DOC-01 :** terminé pour le développement indépendant du système A. L'intégration finale liée à l'authentification et à l'isolation des utilisateurs reste dépendante des tickets transversaux concernés.
- **DOC-02 :** terminé pour le développement indépendant du système A. Le traitement MinerU et la normalisation sont implémentés dans le cadre convenu.
- **DOC-03 :** prochain ticket à implémenter ; ce document fournit à l'agent IA le contexte du backlog.
- **VIS-01, VIS-02, RAG-01, RAG-02 et RAG-03 :** à réaliser selon le backlog et leurs dépendances.

> « Terminé indépendamment » ne signifie pas que toutes les intégrations transversales sont achevées. En particulier, l'authentification et l'isolation des données doivent être raccordées lorsque les tickets AUTH correspondants seront disponibles.

## 3. Tickets transversaux

### 3.1. Architecture et contrats partagés

| ID | Titre | Description du backlog | Priorité | Estimation | Dépendances |
|---|---|---|---|---:|---|
| ARC-01 | Conventions du dépôt et exécution des tests | Définir la structure du dépôt, les conventions, les commandes d'exécution et de test, ainsi que les règles de branches et de pull requests. | P0 | 2 | Aucune |
| ARC-02 | Contrat commun des documents | Définir les contrats partagés relatifs aux documents, états, passages, références, ressources visuelles et erreurs. | P0 | 3 | ARC-01 |
| ARC-03 | Contrats pédagogiques et du modèle apprenant | Définir les contrats relatifs à la génération, aux QCM, aux réponses, aux concepts, aux observations, aux estimations et aux recommandations. | P0 | 3 | ARC-01 |
| ARC-04 | Fixtures partagées et doubles de test | Préparer des jeux de données et des interfaces simulées pour tester les interactions entre A, B et C. | P0 | 3 | ARC-02, ARC-03 |

### 3.2. Authentification et isolation des données

| ID | Titre | Description du backlog | Priorité | Estimation | Dépendances |
|---|---|---|---|---:|---|
| AUTH-01 | Authentification classique et Google OAuth 2.0 | Mettre en place l'inscription, la connexion, la déconnexion, l'authentification Google et la gestion des erreurs associées. | P1 | 5 | ARC-01 |
| AUTH-02 | Isolation des données par utilisateur | Garantir l'accès uniquement aux documents, tentatives et profils appartenant à l'utilisateur ; ajouter des tests inter-utilisateurs. | P1 | 3 | AUTH-01, ARC-02, ARC-03 |

**État connu :** le développeur responsable d'AUTH-01 et AUTH-02 ne les a pas encore terminés. Le développement indépendant de DOC-01 et DOC-02 a néanmoins été réalisé. Les intégrations qui nécessitent réellement l'authentification ou l'isolation finale restent à raccorder.

### 3.3. Intégration et livraison

| ID | Titre | Description du backlog | Priorité | Estimation | Dépendances |
|---|---|---|---|---:|---|
| INT-01 | Intégrer les modules A/B/C | Appels internes conformes aux contrats, gestion des erreurs et cohérence des données. | P1 | 3 | ARC-02 à ARC-04 et modules concernés |
| INT-02 | Valider le parcours complet de bout en bout | Parcours MVP : importer un PDF, générer un QCM, répondre, obtenir la correction, consulter l'historique et recevoir une recommandation basée sur une observation valide. | P1 | 5 | INT-01, UI-02 à UI-05 |
| INT-03 | Sécuriser le parcours intégré | Tests de bout en bout prouvant l'absence d'accès inter-utilisateurs dans le système intégré. | P1 | 2 | INT-02, AUTH-02 |
| REL-01 | Documenter le lancement et la démonstration | Préparer la documentation nécessaire au lancement et à la démonstration du projet. | P1 | 2 | INT-01 |

## 4. Dépendances importantes pour le système A

| Ticket A | Dépendance | Pourquoi elle compte |
|---|---|---|
| DOC-01 | AUTH-02 | L'accès aux documents doit finalement être limité à leur propriétaire. Le traitement indépendant peut être développé avec les mécanismes de test existants, sans inventer une authentification parallèle. |
| DOC-01 | ARC-02 | Le modèle et le cycle de vie des documents doivent respecter le contrat commun. |
| DOC-02 | DOC-01 | DOC-02 traite un PDF déjà enregistré par DOC-01 et réutilise son modèle et son stockage. |
| DOC-02 | ARC-02 | La représentation documentaire, les états, les références et les erreurs doivent rester compatibles avec le contrat commun. |
| DOC-03 | AUTH-02 | La liste et la consultation des documents doivent être limitées aux documents du propriétaire authentifié. |
| DOC-03 | DOC-01 | DOC-03 expose les documents et les états déjà gérés par DOC-01. |
| VIS-01 | DOC-02 | Les figures et leurs métadonnées proviennent de l'extraction et de la normalisation. |
| VIS-01 / VIS-02 | ARC-02 | Les références visuelles et leurs relations doivent respecter les conventions partagées. |
| RAG-01 | DOC-02 | Le découpage s'effectue à partir du contenu documentaire normalisé. |
| RAG-01 / RAG-02 | ARC-02 | Les passages et leurs références doivent suivre le contrat documentaire commun. |
| RAG-03 | VIS-02 | Le service de recherche doit pouvoir retourner les figures associées aux passages. |
| RAG-03 | ARC-04 | Les fixtures et doubles partagés facilitent les tests du service de recherche et de ses interactions. |

## 5. Règles de travail pour un agent IA

1. **Respecter le périmètre du ticket demandé.** Ne pas implémenter spontanément les tickets dépendants ou voisins.
2. **Lire le code existant avant de modifier.** DOC-01 et DOC-02 constituent la base de travail du système A.
3. **Ne pas recréer les fonctionnalités déjà réalisées.** Réutiliser les modèles, services, stockages, contrats et conventions existants.
4. **Respecter les contrats partagés.** En cas de contrat manquant ou ambigu, identifier précisément le point bloquant plutôt que d'inventer silencieusement une nouvelle interface.
5. **Ne pas simuler AUTH-01 ou AUTH-02 en production.** Les tests peuvent utiliser des utilisateurs de test, mais le code applicatif doit rester compatible avec l'authentification et les permissions prévues.
6. **Préserver la séparation des responsabilités.** A prépare les documents, passages, références visuelles et la recherche documentaire ; il ne prend pas en charge la génération pédagogique de B ni le modèle apprenant de C.
7. **Ne pas confondre les états.** `ready` dans DOC-01/DOC-02 signifie que le document a été extrait et normalisé avec succès. Cela ne signifie pas nécessairement que le découpage et l'indexation RAG sont terminés.
8. **Tester les régressions.** Exécuter les tests du ticket courant et ceux des fonctionnalités A déjà réalisées.
9. **Signaler les dépendances non disponibles.** Distinguer ce qui peut être développé indépendamment de ce qui attend réellement un contrat ou une intégration.
10. **Ne pas modifier le backlog.** Toute modification de titre, estimation, priorité ou dépendance nécessite une décision de l'équipe.

## 6. Contrat A → B déjà convenu

Ce contrat est rappelé pour éviter qu'un agent IA ne le redéfinisse lors d'un ticket ultérieur.

### Requête B → A

```python
request = {
    "document_id": "doc_123",
    "query": (
        "Organisation des threads et des blocs CUDA, "
        "indices et dimensions d'exécution"
    ),
    "page_range": {
        "start": 10,
        "end": 18
    },
    "top_k": 5
}
```

- `document_id` identifie le document à interroger.
- `query` exprime le besoin informationnel formulé par B.
- `page_range` est un périmètre facultatif.
- `top_k` indique le nombre maximal de passages les mieux classés à retourner.

B formule la requête sémantique. A effectue la recherche. A ne doit pas recevoir systématiquement le prompt complet de génération de B pour en extraire lui-même des mots-clés.

### Réponse A → B

```python
response = {
    "document_id": "doc_123",
    "results": [
        {
            "chunk_id": "chk_045",
            "text": (
                "Un bloc est un groupe de threads qui peuvent "
                "coopérer et partager certaines ressources..."
            ),
            "relevance_score": 0.87,
            "source": {
                "page_start": 5,
                "page_end": 5,
                "section_title": "Organisation de l'exécution",
                "block_ids": ["blk_078", "blk_079"]
            },
            "visual_assets": [
                {
                    "asset_id": "img_012",
                    "page": 5,
                    "caption": "Organisation des threads en blocs",
                    "access_path": (
                        "/api/documents/doc_123/assets/img_012"
                    )
                }
            ]
        }
    ]
}
```

Ce contrat est un rappel de l'accord existant, pas une demande de l'implémenter dans DOC-03. Il sera mis en œuvre dans les tickets RAG concernés et intégré avec B conformément aux tickets transversaux.

## 7. Limites de ce document

- Les tickets B, C et UI ne sont pas détaillés ici, à l'exception de leurs identifiants lorsqu'ils apparaissent comme dépendances.
- Les critères d'acceptation détaillés n'étaient pas fournis dans les entrées initiales du backlog ; les descriptions ci-dessus ne doivent pas être présentées comme des critères d'acceptation exhaustifs.
- Les états d'avancement sont ceux connus au moment de la rédaction et peuvent évoluer.
- Une dépendance inscrite dans le backlog ne justifie pas de créer une implémentation provisoire incompatible avec le contrat final.
- Si le dépôt contient une décision plus récente validée par l'équipe, l'agent doit la signaler et demander confirmation avant de remplacer un contrat partagé.

**Ce fichier est un document de contexte pour les agents IA et les développeurs. Il complète les prompts de tickets ; il ne les remplace pas.**
