# Workflow de Release avec Candidates et Hotfix

Ce document décrit le workflow de gestion des patches et releases avec le système de candidates et hotfix.

## Vision et Motivation

### Problème du workflow actuel

Dans le workflow actuel, les patches sont ajoutés directement à `ho-prod` via `patch add`. Les développeurs ont pris l'habitude de créer des releases RC pour un seul patch, car :
- Les patches ne sont pas visibles avant d'être en RC
- Ils préfèrent faire une pre-release pour rendre le patch accessible
- `ho-prod` est "pollué" avec des patches avant même d'avoir un RC

### Solution : Branche d'intégration `ho-release/X.Y.Z`

Le nouveau workflow introduit une **vraie branche de travail** `ho-release/X.Y.Z` qui sert de **sandbox d'intégration** :
- Les patches sont visibles et testables sur `ho-release/X.Y.Z` avant d'atterrir sur `ho-prod`
- `ho-prod` reste stable et ne contient que des versions validées (RC ou production)
- Pas besoin de créer un RC juste pour rendre un patch accessible
- Workflow Git-Flow qui colle aux pratiques GitLab/GitHub (milestones, MR, issues)

## Concepts clés

### Fichiers de release

```
releases/
├── 0.1.0-candidates.txt   # Patches en préparation pour 0.1.0
├── 0.1.0-stage.txt        # Patches intégrés (en attente de RC)
├── 0.1.0-rc1.txt          # Premier Release Candidate
├── 0.1.0-rc2.txt          # Deuxième RC (corrections)
├── 0.1.0.txt              # Version production
├── 0.1.0-hotfix1.txt      # Hotfix urgent sur prod
└── 0.2.0-candidates.txt   # Prochaine release en cours
```

### États d'un patch

1. **Candidate** : Patch assigné à une release, en cours de développement (dans `-candidates.txt`)
2. **Staged** : Patch intégré dans la branche `ho-release/X.Y.Z`, en attente de promotion (dans `-stage.txt`)
3. **Released** : Patch inclus dans une release déployée en production (dans `X.Y.Z.txt`)

### États d'une release

1. **Preparation** : Release en cours de préparation avec patches candidats et/ou stagés (fichiers `-candidates.txt` et `-stage.txt`)
2. **RC (Release Candidate)** : Release taguée pour tests, prête pour validation (tag `vX.Y.Z-rcN`, fichier `-rcN.txt`)
3. **Production** : Release déployée en production, mergée dans `ho-prod` (tag `vX.Y.Z`, fichier `X.Y.Z.txt`)
4. **Hotfix** : Release de correction urgente sur une version déjà en production (tag `vX.Y.Z-hotfixN`, fichier `X.Y.Z-hotfixN.txt`)

### Analogie avec GitLab/GitHub

| État half-orm | Fichier | GitLab/GitHub |
|---------------|---------|---------------|
| `release new` | Crée `-candidates.txt` et `-stage.txt` | Créer un milestone |
| `patch new` (sur ho-release) | Ajoute à `-candidates.txt` | Créer une issue assignée au milestone |
| Candidate | `-candidates.txt` | Issue ouverte assignée au milestone |
| `patch close` | Déplace vers `-stage.txt` | Merger la MR et fermer l'issue |
| Stage | `-stage.txt` | Issue fermée du milestone |
| `release promote rc` | Renomme en `-rcN.txt` | Créer une pre-release |
| RC | `-rcN.txt` | Pre-release GitHub |
| `release promote prod` | Renomme en `X.Y.Z.txt` | Créer une release stable |
| Production | `X.Y.Z.txt` | Release stable |

## Workflow standard (développement planifié)

### 1. Créer une nouvelle release

```bash
half_orm dev release new minor
# → Détecte la version prod actuelle (ex: 0.0.5)
# → Calcule la prochaine version minor : 0.1.0
# → Crée la branche ho-release/0.1.0 depuis ho-prod
# → Crée releases/0.1.0-candidates.txt (vide)
# → Crée releases/0.1.0-stage.txt (vide)
# → Commit et push pour réserver la version globalement
# → Switch automatiquement sur ho-release/0.1.0
```

**Sortie** :
```
✅ Release created successfully!

  Version:          0.1.0
  Release branch:   ho-release/0.1.0
  Stage file:       releases/0.1.0-stage.txt

📝 Next steps:
  1. Create patches: half_orm dev patch new <patch_id>
  2. Add to release: half_orm dev patch close <patch_id>
  3. Promote to RC:  half_orm dev release promote rc

ℹ️  Patches will be merged into ho-release/0.1.0 for integration testing
```

### 2. Créer un patch candidat

**Prérequis** : Être sur la branche `ho-release/0.1.0`

```bash
git checkout ho-release/0.1.0
half_orm dev patch new 6-feature-x
# → Détecte automatiquement la version 0.1.0 depuis la branche courante
# → Crée ho-patch/6-feature-x depuis ho-release/0.1.0
# → Ajoute 6-feature-x à 0.1.0-candidates.txt
# → Switch sur ho-patch/6-feature-x
```

**Note importante** :
- Si vous n'êtes pas sur une branche `ho-release/*`, la commande échoue avec un message d'erreur
- Pour les corrections urgentes sur production, utilisez `half_orm dev hotfix` d'abord
- Le patch est **automatiquement ajouté** à `0.1.0-candidates.txt` lors de la création (pas de planification manuelle requise)

**Sortie** :
```
✓ Created patch branch: ho-patch/6-feature-x
✓ Created patch directory: Patches/6-feature-x/
✓ Switched to branch: ho-patch/6-feature-x

📝 Next steps:
  1. Add SQL/Python files to Patches/6-feature-x/
  2. Run: half_orm dev patch apply
  3. Test your changes
  4. Run: half_orm dev patch close 6-feature-x
```

Le développeur travaille sur son patch...

### 3. Synchroniser avec les autres patches intégrés

Quand un autre patch est intégré dans la release, les patches candidats doivent se mettre à jour :

```bash
git fetch origin
git merge origin/ho-release/0.1.0
```

### 4. Fermer le patch (intégrer à la release)

```bash
half_orm dev patch close 6-feature-x
# Workflow complet :
# → Détecte la version depuis 0.1.0-candidates.txt
# → Vérifie que ho-patch/6-feature-x existe
# → Merge ho-patch/6-feature-x dans ho-release/0.1.0
# → Déplace 6-feature-x de candidates.txt vers stage.txt
# → Supprime la branche ho-patch/6-feature-x
# → Commit et push les changements
# → Notifie les autres patches candidats qu'ils doivent se synchroniser
```

**Sortie** :
```
✓ Patch closed successfully!

  Stage file:      releases/0.1.0-stage.txt
  Patch added:     6-feature-x
  Tests passed:    ✓
  Notified:        2 active branch(es)

📝 Next steps:
  • Other developers: git pull && git rebase ho-release/0.1.0
  • Continue development: half_orm dev patch new <next_patch_id>
  • Promote to RC: half_orm dev release promote rc
```

**Important** : `patch close` remplace l'ancienne commande `patch add`. La sémantique est différente :
- **Ancien** : `patch add` = "j'ajoute mon patch validé à la release" (depuis ho-prod)
- **Nouveau** : `patch close` = "je ferme mon travail, il est intégré à la release" (merge dans ho-release)

### 5. Promouvoir en Release Candidate

**Règle de séquentialité** : On ne peut promouvoir en RC que **la plus petite version** en préparation. Cela garantit l'ordre séquentiel des releases.

**Exemple** : Si les releases `0.1.1`, `0.2.0` et `1.0.0` sont en préparation, seule `0.1.1` peut être promue en RC.

```bash
half_orm dev release promote rc
# Workflow complet :
# → Détecte automatiquement la plus petite version avec -stage.txt
# → Vérifie qu'elle est bien séquentielle (suit la dernière prod/RC)
# → Switch automatiquement sur ho-release/X.Y.Z
# → Trouve le prochain numéro RC (rc1, rc2, etc.)
# → Crée le tag vX.Y.Z-rc1 sur ho-release/X.Y.Z (PAS sur ho-prod!)
# → Renomme releases/X.Y.Z-stage.txt en releases/X.Y.Z-rc1.txt (git mv)
# → Recrée releases/X.Y.Z-stage.txt (vide) pour les prochains patches
# → Commit et push
```

**Sortie** :
```
✓ Success!

  Version:  0.1.0
  Tag:      v0.1.0-rc1
  Branch:   ho-release/0.1.0

📝 Next steps:
  • Test RC thoroughly
  • Deploy to production: half_orm dev release promote prod
```

**Notes importantes** :
- Le tag est créé sur `ho-release/0.1.0`, **pas sur `ho-prod`**
- La commande **détecte automatiquement** quelle version promouvoir (la plus petite)
- Impossible de "sauter" une version : si 0.1.0 n'est pas en prod, on ne peut pas promouvoir 0.2.0

### 6. Promouvoir en production

**Règle de séquentialité** : Comme pour les RC, on ne peut promouvoir en production que **le plus petit RC** disponible.

```bash
half_orm dev release promote prod
# Workflow complet :
# → Détecte automatiquement le plus petit RC disponible (ex: 0.1.0-rc1)
# → Vérifie la séquentialité stricte (0.1.0 doit suivre la dernière prod)
# → Switch automatiquement sur ho-prod
# → Merge ho-release/0.1.0 dans ho-prod (intégration du code des patches)
# → Restore database et applique tous les patches de tous les RC + stage
# → Génère model/schema-0.1.0.sql et metadata-0.1.0.sql
# → Met à jour le symlink model/schema.sql → schema-0.1.0.sql
# → Renomme le dernier RC file en releases/0.1.0.txt (liste finale)
# → Supprime releases/0.1.0-candidates.txt et releases/0.1.0-stage.txt
# → Conserve releases/0.1.0-rc*.txt pour l'historique
# → Crée le tag v0.1.0 sur ho-prod
# → Supprime la branche ho-release/0.1.0 (mission accomplie)
# → Commit et push
```

**Sortie** :
```
✓ Success!

  Version:          0.1.0
  Tag:              v0.1.0
  Branches deleted: ho-release/0.1.0

📝 Next steps:
  • Deploy to production servers
  • Start next cycle: half_orm dev release new minor
```

**Notes importantes** :
- C'est à ce moment que le code des patches est **vraiment mergé dans `ho-prod`**, pas avant
- La commande **détecte automatiquement** quel RC promouvoir (le plus petit)
- La séquentialité est **strictement respectée** : impossible de promouvoir 0.2.0 si 0.1.0 n'est pas déjà en prod

## Workflow hotfix (correction urgente)

### Scénario

Un bug critique est découvert en production (v0.2.0) alors qu'une nouvelle release (v0.3.0) est déjà en cours de développement. Il faut corriger la production **sans attendre** la v0.3.0.

### 1. Réouvrir la version de production

```bash
half_orm dev hotfix
# Workflow :
# → Détecte la version en production depuis model/schema.sql (ex: 0.2.0)
# → Vérifie que le tag v0.2.0 existe
# → Réouvre la branche ho-release/0.2.0 à partir du tag v0.2.0
# → Switch automatiquement sur ho-release/0.2.0
```

**Sortie** :
```
✓ Reopened ho-release/0.2.0 from v0.2.0
✓ Ready for hotfix patches

📝 Next steps:
  1. half_orm dev patch new <patch_id>
  2. half_orm dev patch close <patch_id>
  3. half_orm dev release promote hotfix
```

**Note importante** : C'est une **rupture du workflow séquentiel** car on a maintenant deux branches de release actives simultanément (`ho-release/0.2.0` et `ho-release/0.3.0`).

### 2. Créer et intégrer le patch de hotfix

Le workflow est **identique** au workflow normal :

```bash
# Sur ho-release/0.2.0
half_orm dev patch new 999-critical-security-fix
# ... développement ...
half_orm dev patch apply
# ... tests ...
half_orm dev patch close 999-critical-security-fix
```

### 3. Promouvoir le hotfix en production

**Important** : On ne peut pas utiliser `promote prod` car le tag `v0.2.0` existe déjà !

```bash
git checkout ho-prod
half_orm dev release promote hotfix
# Workflow spécifique hotfix :
# → Détecte qu'on est dans un contexte hotfix (tag vX.Y.Z existe déjà)
# → Trouve le prochain numéro de hotfix (hotfix1, hotfix2, etc.)
# → Merge ho-release/0.2.0 dans ho-prod
# → Génère model/schema-0.2.0-hotfix1.sql et metadata-0.2.0-hotfix1.sql
# → Met à jour le symlink model/schema.sql → schema-0.2.0-hotfix1.sql
# → Crée releases/0.2.0-hotfix1.txt avec la liste des patches
# → Crée le tag v0.2.0-hotfix1 sur ho-prod
# → Supprime la branche ho-release/0.2.0
# → Commit et push
```

**Sortie** :
```
✓ Hotfix deployed!

  Version:  0.2.0-hotfix1
  Tag:      v0.2.0-hotfix1
  Patches:  999-critical-security-fix

📝 Next steps:
  • Deploy to production servers immediately
  • Sync other releases: git checkout ho-release/0.3.0 && git merge ho-prod
```

### 4. Synchroniser les autres releases en cours

Si une release est en cours de développement (ex: 0.3.0), elle **doit** intégrer le hotfix :

```bash
git checkout ho-release/0.3.0
git merge ho-prod
# Résout les conflits éventuels
git push origin ho-release/0.3.0
```

Cela garantit que le bugfix ne sera pas perdu lors de la prochaine release.

## Notifications et synchronisation

### Après `patch close`

Le système affiche les patches candidats qui doivent se synchroniser :

```
✓ Patch 6-feature-x intégré dans release 0.1.0

⚠️  2 patches candidats doivent se mettre à jour avec ho-release/0.1.0 :
  • ho-patch/8-other-feature - 3 commits en retard
  • ho-patch/9-another - 1 commit en retard

Commande suggérée :
  git fetch origin && git merge origin/ho-release/0.1.0
```

### Commande `check`

La commande `half_orm dev check` affiche l'état complet :

```
📍 Current branch: ho-patch/8-other-feature

🔧 Patch branches (2):
  → • ho-patch/8-other-feature - ✓ synced
    • ho-patch/9-another - ↑ 2 ahead

📦 Release 0.1.0 en cours:
  Intégrés (stage):
    • 6-feature-x

  Candidats:
    • 8-other-feature - ⚠️ 3 commits en retard
    • 9-another - ✓ à jour
```

## Visualisation avec `half_orm dev check`

La commande `half_orm dev check` affiche l'état complet de toutes les releases en cours. Utilisation recommandée **fréquemment** par les développeurs pour se synchroniser.

**Exemple de sortie multi-releases** :

```
📍 Current branch: ho-patch/42-feature-x

📦 Release 0.2.0 (ho-release/0.2.0):
  Stage (intégrés):
    • 38-auth ✓
    • 39-api ✓

  Candidates (en cours):
    • 42-feature-x ⚠️ 2 commits en retard (vous)
    • 45-ui ✓ à jour (alice)
    • 47-db ↑ 1 commit en avance (bob)

📦 Release 0.3.0 (ho-release/0.3.0):
  Candidates:
    • 50-refactor (charlie)

⚠️ Actions recommandées:
  • Votre patch est en retard de 2 commits sur ho-release/0.2.0
  • Commande: git fetch origin && git merge origin/ho-release/0.2.0
```

Cette commande permet de :
- Voir l'état de toutes les releases actives
- Identifier quels patches sont en retard sur leur branche d'intégration
- Savoir qui travaille sur quoi
- Détecter les releases prêtes à être promues

## Règle de séquentialité des releases

### Principe

Les releases doivent être promues **dans l'ordre séquentiel strict**. On ne peut pas "sauter" une version.

### Exemples

**✅ Valide** :
- Production actuelle : `0.1.0`
- Prochaine promotion possible : `0.1.1` (patch), `0.2.0` (minor), ou `1.0.0` (major)

**❌ Invalide** :
- Production actuelle : `0.1.0`
- Releases en préparation : `0.1.1`, `0.2.0`, `1.0.0`
- Tentative de promouvoir `0.2.0` → **ERREUR** : il faut d'abord promouvoir `0.1.1`

### Pourquoi cette règle ?

1. **Cohérence des schémas** : Les patches SQL s'appliquent séquentiellement sur le schéma
2. **Traçabilité** : On sait exactement quels patches ont été appliqués dans quel ordre
3. **Rollback simplifié** : En cas de problème, on revient à la version précédente connue
4. **Prévention des erreurs** : Impossible d'oublier une release "au milieu"

### Détection automatique

Les commandes `release promote rc` et `release promote prod` **détectent automatiquement** la plus petite version à promouvoir. Vous n'avez pas besoin de spécifier la version.

```bash
# Releases en préparation : 0.1.1-stage.txt, 0.2.0-stage.txt, 1.0.0-stage.txt
half_orm dev release promote rc
# → Promouvoir automatiquement 0.1.1 (la plus petite)

# Si vous êtes sur la branche ho-release/0.2.0, la commande échouera :
git checkout ho-release/0.2.0
half_orm dev release promote rc
# ❌ Error: Cannot promote 0.2.0: must promote versions sequentially.
#    Last production: 0.1.0
#    Next in sequence: 0.1.1
```

### Exception : Hotfixes

Les hotfixes sont la **seule exception** à cette règle car ils rouvrent une version déjà en production pour correction urgente. Voir [Workflow hotfix](#workflow-hotfix-correction-urgente).

---

## Avantages de cette approche

1. **Visibilité** : On sait toujours quels patches sont en cours pour quelle release (via `-candidates.txt`)
2. **Stabilité de `ho-prod`** : Ne contient que du code validé en RC, pas de "pollution"
3. **Testabilité** : Les patches sont testables sur `ho-release/X.Y.Z` avant d'atteindre production
4. **Synchronisation** : `half_orm dev check` permet aux développeurs de rester à jour
5. **Traçabilité** : Historique complet des RC et hotfixes dans `releases/`
6. **Flexibilité** : Support des hotfixes sans perturber le développement en cours
7. **Simplicité** : Pas de planification manuelle requise - ajout automatique lors de `patch new`
8. **Compatibilité GitLab/GitHub** : Workflow familier pour les développeurs habitués aux milestones et MR
9. **Séquentialité garantie** : Impossible de promouvoir les versions dans le désordre

## Cas d'usage

### Développement normal

```bash
# Planification
half_orm dev release new minor                    # 0.2.0

# Développement parallèle (chaque dev sur ho-release/0.2.0)
git checkout ho-release/0.2.0
half_orm dev patch new 10-auth                    # Dev A
half_orm dev patch new 11-api                     # Dev B
half_orm dev patch new 12-ui                      # Dev C

# Intégration séquentielle
half_orm dev patch close 10-auth                  # Dev A termine
# Dev B et C se synchronisent avec ho-release/0.2.0 (git rebase ou git merge)
half_orm dev patch close 11-api                   # Dev B termine
half_orm dev patch close 12-ui                    # Dev C termine

# Release
half_orm dev release promote rc                   # Test
half_orm dev release promote prod                 # Déploiement
```

### Bug critique en production

```bash
# Hotfix urgent (prod = v0.2.0, dev en cours = v0.3.0)
half_orm dev hotfix
# → Réouvre ho-release/0.2.0 depuis tag v0.2.0

# Même workflow que d'habitude
half_orm dev patch new 999-critical-fix
half_orm dev patch close 999-critical-fix

# Promotion spécifique hotfix
git checkout ho-prod
half_orm dev release promote hotfix
# → Génère v0.2.0-hotfix1

# Synchroniser la release en cours pour intégrer le fix
git checkout ho-release/0.3.0
git merge ho-prod
```

### Plusieurs RC avant production

```bash
half_orm dev release promote rc                   # v0.2.0-rc1
# Bug trouvé en test
# toujours sur la branche ho-release/0.2.0
half_orm dev patch new 13-fix-test
half_orm dev patch close 13-fix-test
half_orm dev release promote rc                   # v0.2.0-rc2
# OK
half_orm dev release promote prod                 # v0.2.0
```

---

## Plan de refactoring

### Vue d'ensemble des changements

| Commande | Workflow actuel | Workflow cible | Changements requis |
|----------|----------------|----------------|-------------------|
| `release new` | Crée `-stage.txt`, reste sur `ho-prod` | Crée `ho-release/X.Y.Z` + `-candidates.txt` + `-stage.txt`, switch sur branche | ✅ Adapter ReleaseManager |
| `patch new` | Depuis `ho-prod` | Depuis `ho-release/*`, ajoute à `-candidates.txt` | ✅ Adapter PatchManager |
| `patch add` | Merge dans `ho-prod` | **Renommer en `patch close`**, merge dans `ho-release/*`, déplace vers `-stage.txt` | ✅ Refactor complet |
| `release promote rc` | Tag sur `ho-prod` | Tag sur `ho-release/*` (pas ho-prod!) | ✅ Adapter ReleaseManager |
| `release promote prod` | Tag et dumps | Merge `ho-release/*` → `ho-prod`, tag et dumps | ✅ Adapter ReleaseManager |
| `hotfix` | ❌ Non implémenté | Réouvre `ho-release/*` depuis tag | ✅ Nouvelle commande |

### Phases d'implémentation

#### Phase 1 : Adapter `release new`
**Objectif** : Créer une vraie branche d'intégration au lieu de juste un fichier.

**Fichiers à modifier** :
- `half_orm_dev/release_manager.py` : Méthode `new_release()`
- `half_orm_dev/cli/commands/release.py` : Sortie de la commande

**Changements** :
```python
# Dans ReleaseManager.new_release()
def new_release(self, level: str) -> dict:
    # 1. Calculer la version
    version = self._calculate_next_version(level)

    # 2. NOUVEAU : Créer la branche ho-release/X.Y.Z depuis ho-prod
    release_branch = f"ho-release/{version}"
    self.repo.hgit.create_branch(release_branch, from_branch="ho-prod")

    # 3. Créer les fichiers (NOUVEAU : candidates.txt en plus)
    candidates_file = self.repo.path / "releases" / f"{version}-candidates.txt"
    candidates_file.write_text("")
    stage_file = self.repo.path / "releases" / f"{version}-stage.txt"
    stage_file.write_text("")

    # 4. Commit et push
    self.repo.hgit.add([candidates_file, stage_file])
    self.repo.hgit.commit(f"[release] Prepare {version}")
    self.repo.hgit.push()

    # 5. NOUVEAU : Switch sur la branche de release
    self.repo.hgit.checkout(release_branch)

    return {
        "version": version,
        "branch": release_branch,
        "stage_file": str(stage_file.relative_to(self.repo.path))
    }
```

**Tests à effectuer** :
- ✅ Vérifier que `ho-release/X.Y.Z` est créée depuis `ho-prod`
- ✅ Vérifier que `-candidates.txt` et `-stage.txt` sont créés vides
- ✅ Vérifier le switch automatique sur `ho-release/X.Y.Z`

---

#### Phase 2 : Adapter `patch new`
**Objectif** : Créer les patches depuis `ho-release/*` au lieu de `ho-prod`.

**Fichiers à modifier** :
- `half_orm_dev/patch_manager.py` : Méthode `create_patch()`
- `half_orm_dev/cli/commands/patch.py` : Validation et sortie

**Changements** :
```python
# Dans PatchManager.create_patch()
def create_patch(self, patch_id: str, description: str = None) -> dict:
    current_branch = self.repo.hgit.branch

    # NOUVEAU : Vérifier qu'on est sur ho-release/*
    if not current_branch.startswith('ho-release/'):
        raise PatchManagerError(
            f"Must be on ho-release/* branch. Current: {current_branch}\n"
            f"Use: half_orm dev release new <level> first\n"
            f"For production hotfixes, use: half_orm dev hotfix"
        )

    # Extraire la version depuis la branche
    version = current_branch.replace('ho-release/', '')

    # Créer la branche de patch depuis ho-release/X.Y.Z (pas ho-prod!)
    patch_branch = f"ho-patch/{patch_id}"
    self.repo.hgit.create_branch(patch_branch, from_branch=current_branch)

    # NOUVEAU : Ajouter automatiquement à candidates.txt
    candidates_file = self.repo.path / "releases" / f"{version}-candidates.txt"

    # Éviter les doublons si le patch est déjà listé (planification manuelle)
    existing_candidates = candidates_file.read_text().strip().split('\n') if candidates_file.exists() else []
    if patch_id not in existing_candidates:
        with candidates_file.open('a') as f:
            f.write(f"{patch_id}\n")

    # Créer le répertoire Patches/
    patch_dir = self.repo.path / "Patches" / patch_id
    patch_dir.mkdir(parents=True, exist_ok=True)

    # Commit et switch
    self.repo.hgit.add([candidates_file, patch_dir])
    self.repo.hgit.commit(f"[patch] Add candidate {patch_id} to {version}")
    self.repo.hgit.push()
    self.repo.hgit.checkout(patch_branch)

    return {
        "branch_name": patch_branch,
        "patch_dir": patch_dir,
        "version": version,
        "on_branch": self.repo.hgit.branch
    }
```

**Tests à effectuer** :
- ✅ Erreur si pas sur `ho-release/*`
- ✅ Branche créée depuis `ho-release/X.Y.Z` (pas ho-prod)
- ✅ Patch ajouté à `-candidates.txt`

---

#### Phase 3 : Renommer et adapter `patch add` → `patch close`
**Objectif** : Changer la sémantique : merge dans `ho-release/*` au lieu de `ho-prod`.

**Fichiers à modifier** :
- `half_orm_dev/patch_manager.py` : Nouvelle méthode `close_patch()`
- `half_orm_dev/cli/commands/patch.py` : Nouvelle commande `patch close`

**Changements** :
```python
# Dans PatchManager.close_patch()
def close_patch(self, patch_id: str) -> dict:
    # 1. Détecter la version depuis candidates.txt
    version = self._find_version_for_candidate(patch_id)
    if not version:
        raise PatchManagerError(
            f"Patch {patch_id} not found in any candidates file.\n"
            f"Available patches:\n{self._list_all_candidates()}"
        )

    release_branch = f"ho-release/{version}"
    patch_branch = f"ho-patch/{patch_id}"

    # 2. Vérifier que la branche de patch existe
    if not self.repo.hgit.branch_exists(patch_branch):
        raise PatchManagerError(f"Branch {patch_branch} does not exist")

    # 3. Merger dans ho-release/X.Y.Z (PAS dans ho-prod!)
    self.repo.hgit.checkout(release_branch)
    self.repo.hgit.merge(patch_branch)

    # 4. Déplacer de candidates vers stage
    self._move_patch_to_stage(patch_id, version)

    # 5. Supprimer la branche de patch
    self.repo.hgit.delete_branch(patch_branch)

    # 6. Commit et push
    self.repo.hgit.commit(f"[patch] Close {patch_id} for {version}")
    self.repo.hgit.push()

    # 7. BONUS : Notifier les autres patches candidats
    other_candidates = self._get_other_candidates(version, patch_id)

    return {
        "version": version,
        "patch_id": patch_id,
        "stage_file": f"releases/{version}-stage.txt",
        "merged_into": release_branch,
        "notified_branches": other_candidates
    }
```

**Tests à effectuer** :
- ✅ Détection version depuis `-candidates.txt`
- ✅ Merge dans `ho-release/*` (pas ho-prod)
- ✅ Déplacement candidates → stage
- ✅ Suppression de la branche

---

#### Phase 4 : Adapter `release promote rc`
**Objectif** : Tag sur `ho-release/*` au lieu de `ho-prod` + respecter la séquentialité.

**Fichiers à modifier** :
- `half_orm_dev/release_manager.py` : Méthode `promote_to_rc()`

**Changements clés** :
```python
def promote_to_rc(self) -> dict:
    # 1. Détecter automatiquement la plus petite version avec -stage.txt
    smallest_stage = self._find_smallest_stage_version()
    if not smallest_stage:
        raise ReleaseManagerError("No stage release found to promote")

    # 2. Vérifier la séquentialité stricte
    last_prod_version = self._get_production_version()
    if not self._is_sequential(last_prod_version, smallest_stage):
        raise ReleaseManagerError(
            f"Cannot promote {smallest_stage}: must promote versions sequentially.\n"
            f"Last production: {last_prod_version}"
        )

    # 3. Switch sur la branche ho-release/X.Y.Z
    release_branch = f"ho-release/{smallest_stage}"
    self.repo.hgit.checkout(release_branch)

    # 4. Trouver le prochain RC number
    rc_num = self._next_rc_number(smallest_stage)

    # 5. Tag sur ho-release/X.Y.Z (PAS sur ho-prod!)
    tag = f"v{smallest_stage}-rc{rc_num}"
    self.repo.hgit.create_tag(tag)

    # 6. Renommer stage → rcN
    self._git_mv(
        f"releases/{smallest_stage}-stage.txt",
        f"releases/{smallest_stage}-rc{rc_num}.txt"
    )

    # 7. Recréer stage vide
    stage_file = self.repo.path / "releases" / f"{smallest_stage}-stage.txt"
    stage_file.write_text("")

    # 8. Commit et push
    self.repo.hgit.add([stage_file])
    self.repo.hgit.commit(f"[release] Promote {smallest_stage} to rc{rc_num}")
    self.repo.hgit.push()

    return {
        "version": smallest_stage,
        "tag": tag,
        "branch": release_branch,
        "rc_number": rc_num
    }
```

**Tests à effectuer** :
- ✅ Détection automatique de la plus petite version
- ✅ Erreur si violation de séquentialité
- ✅ Tag créé sur `ho-release/*` (pas ho-prod)
- ✅ Switch automatique sur la bonne branche

---

#### Phase 5 : Adapter `release promote prod`
**Objectif** : Merger `ho-release/*` dans `ho-prod` avant de tag + respecter la séquentialité.

**Fichiers à modifier** :
- `half_orm_dev/release_manager.py` : Méthode `promote_to_prod()`

**Changements clés** :
```python
def promote_to_prod(self) -> dict:
    # 1. Détecter automatiquement le plus petit RC disponible
    smallest_rc = self._find_smallest_rc_version()
    if not smallest_rc:
        raise ReleaseManagerError("No RC found to promote to production")

    # 2. Vérifier la séquentialité stricte
    last_prod_version = self._get_production_version()
    if not self._is_sequential(last_prod_version, smallest_rc):
        raise ReleaseManagerError(
            f"Cannot promote {smallest_rc}: must promote versions sequentially.\n"
            f"Last production: {last_prod_version}"
        )

    # 3. Switch sur ho-prod
    self.repo.hgit.checkout("ho-prod")

    # 4. NOUVEAU : Merger ho-release/X.Y.Z dans ho-prod
    release_branch = f"ho-release/{smallest_rc}"
    self.repo.hgit.merge(release_branch)

    # 5. Générer les dumps SQL
    self._restore_and_apply_patches(smallest_rc)
    self._generate_schema_dump(smallest_rc)
    self._generate_metadata_dump(smallest_rc)
    self._update_schema_symlink(smallest_rc)

    # 6. Renommer le dernier RC en production
    last_rc_file = self._find_latest_rc_file(smallest_rc)
    self._git_mv(last_rc_file, f"releases/{smallest_rc}.txt")

    # 7. Nettoyer les fichiers temporaires
    self._delete_file(f"releases/{smallest_rc}-candidates.txt")
    self._delete_file(f"releases/{smallest_rc}-stage.txt")

    # 8. Tag sur ho-prod
    tag = f"v{smallest_rc}"
    self.repo.hgit.create_tag(tag)

    # 9. Supprimer la branche ho-release/X.Y.Z
    self.repo.hgit.delete_branch(release_branch)

    # 10. Commit et push
    self.repo.hgit.commit(f"[release] Promote {smallest_rc} to production")
    self.repo.hgit.push()

    return {
        "version": smallest_rc,
        "tag": tag,
        "deleted_branches": [release_branch]
    }
```

**Tests à effectuer** :
- ✅ Détection automatique du plus petit RC
- ✅ Erreur si violation de séquentialité
- ✅ Merge de `ho-release/*` dans `ho-prod` avant tout
- ✅ Génération des dumps
- ✅ Suppression de la branche release

---

#### Phase 6 : Implémenter `hotfix`
**Objectif** : Permettre de réouvrir une version de production.

**Fichiers à créer** :
- `half_orm_dev/cli/commands/hotfix.py` (nouvelle commande)
- `half_orm_dev/release_manager.py` : Méthode `reopen_for_hotfix()`
- `half_orm_dev/release_manager.py` : Méthode `promote_to_hotfix()`

---

#### Phase 7 : Améliorer `check`
**Objectif** : Afficher toutes les releases actives et leur état.

**Fichiers à modifier** :
- `half_orm_dev/cli/commands/check.py`
- Nouveau module `half_orm_dev/release_status.py` (optionnel)

**Fonctionnalités** :
- Lister toutes les branches `ho-release/*`
- Pour chaque release, lire `-candidates.txt` et `-stage.txt`
- Comparer les commits entre patches et release branch
- Afficher qui travaille sur quoi

---

### Compatibilité et migration

**Question importante** : Que se passe-t-il avec les releases en cours pendant le refactoring ?

**Stratégie de migration** :
1. **Phase transitoire** : Détecter si on est dans l'ancien ou le nouveau workflow
   - Si `ho-release/X.Y.Z` existe → nouveau workflow
   - Sinon → ancien workflow (compatibility mode)

2. **Migration manuelle** : Pour les releases existantes, proposer une commande :
   ```bash
   half_orm dev release migrate
   # → Crée ho-release/X.Y.Z depuis ho-prod
   # → Migre les fichiers -stage.txt existants
   # → Crée -candidates.txt pour les patches actifs
   ```

3. **Documentation** : Ajouter un guide de migration dans `docs/migration-to-candidates.md`
