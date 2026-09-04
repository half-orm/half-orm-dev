# Journal de développement - half_orm_dev v0.16.0

> ⚠️ **Déprécié / non maintenu.** Ce journal s'arrête à la v0.16.0 et
> n'a pas été tenu à jour depuis. Il reflète l'état et les intentions du
> projet à ce moment-là (ex: noms de commandes, formats de fichiers) et
> ne doit pas être considéré comme une référence sur le comportement
> actuel - voir `docs/half_orm_dev.md` et `BREAKING_CHANGES-1.0.0.md`
> pour l'état courant.

## État actuel du projet

**Date de dernière mise à jour :** 2025-01-29

**Objectif principal :** Migration vers architecture Git-centrique avec workflow `ho-prod` + `ho-patch/`

---

## ✅ Fonctionnalités complètes

### Commande `init-database`
**Status :** Fonctionnelle et testée (260 tests passent)

**Implémentation complète :**
- `Database.setup_database()` - Configuration base de données
- `Database._validate_parameters()` - Validation paramètres
- `Database._collect_connection_params()` - Collecte interactive
- `Database._execute_pg_command()` - Exécution commandes PostgreSQL
- `Database._save_configuration()` - Sauvegarde configuration
- `Database._get_connection_params()` - Accès paramètres

**Fonctionnalités :**
- ✅ Installation automatique métadonnées si `create_db=True`
- ✅ Détection mode (full dev vs sync-only)
- ✅ Gestion interactive des paramètres manquants
- ✅ Messages d'erreur explicites

**Tests :**
- `tests/database/test_load_configuration.py` (14 tests)
- `tests/database/test_get_connection_params.py` (12 tests)
- `tests/test_database_setup.py` (13 tests)

---

### Commande `init-project`
**Status :** ✅ Fonctionnelle (tests manuels validés)

**Implémentation complète :**

**Méthodes Repo.init_git_centric_project() :**
1. ✅ `_validate_package_name()` - Validation nom package Python
2. ✅ `_verify_database_configured()` - Vérification DB configurée
3. ✅ `_detect_development_mode()` - Détection automatique mode
4. ✅ `_create_project_directory()` - Création répertoire projet
5. ✅ `_initialize_configuration()` - Configuration .hop/config
6. ✅ `_create_git_centric_structure()` - Répertoires Patches/, releases/, model/, backups/
7. ✅ `_generate_python_package()` - Génération package Python via modules.generate()
8. ✅ `_generate_template_files()` - Création README, .gitignore, setup.py, Pipfile
9. ✅ `_initialize_git_repository()` - Initialisation Git avec branche ho-prod

**CLI (half_orm_dev/cli/commands/init_project.py) :**
- ✅ Commande `half_orm dev init-project <package_name>`
- ✅ Validation répertoire n'existe pas
- ✅ Messages d'aide et next steps
- ✅ Gestion erreurs avec cleanup

**Fonctionnalités :**
- ✅ Création structure projet complète
- ✅ Commit initial Git sur branche ho-prod avec tous les fichiers
- ✅ Mode auto-détecté (full dev vs sync-only)
- ✅ Messages système avec préfixe `[ho]` (remplace `[hop]`)
- ✅ Génération code Python depuis schéma DB

**Tests :**
- `tests/repo/test_init_validation.py` ✅
- `tests/repo/test_init_mode_detection.py` ✅
- `tests/repo/test_init_configuration.py` ✅
- `tests/repo/test_init_structure.py` ✅
- Tests manuels : ✅ Validés

**Usage :**
```bash
half_orm dev init-database my_db --create-db
half_orm dev init-project my_db
cd my_db
```

**Structure générée :**
```
my_project/
├── .git/              (ho-prod branch, commit initial)
├── .hop/config
├── Patches/          (+ README.md)
├── releases/         (+ README.md)
├── model/
├── backups/
├── my_project/       (package Python généré)
├── tests/
├── README.md
├── .gitignore
├── setup.py
└── Pipfile
```

### Commande `create-patch`
**Status :** ✅ Fonctionnelle (tests OK)

- ✅ Création branche ho-patch/<patch-name>
- ✅ Création répertoire Patches/<patch-name>/
- ✅ Commit répertoire Patches/ sur branche
- ✅ Réservation ID patch via tag (tag-first strategy)
- ✅ Push tag AVANT branche (prévention race conditions)
- ✅ Push branche avec retry (3 tentatives)
- ✅ Gestion transactionnelle avec rollback
- ✅ Checkout automatique vers nouvelle branche
- ✅ Tests unitaires complets (420 tests passent)

**Workflow atomique implémenté :**
1. Validations (ho-prod, repo clean, remote)
2. Création branche locale
3. Création répertoire Patches/
4. Commit "Add Patches/{patch-id} directory"
5. Création tag local (pointe vers commit avec Patches/)
6. **Push tag** → Réservation atomique globale
7. Push branche (3 retry si échec)
8. Checkout vers branche patch

**Garanties transactionnelles :**
- Échec avant push tag → Rollback complet local
- Succès push tag → Réservation garantie (même si push branche échoue)
- Tag-first élimine les race conditions entre développeurs
- Retry automatique push branche (3 tentatives, backoff exponentiel)

**Prévention race conditions :**
- Tag = lock distribué
- Premier à pusher le tag = réservation définitive
- Vérification disponibilité via fetch tags AVANT création locale
- Pas de pollution du remote en cas de conflit

**Tests :**
- `tests/patch_manager/test_patch_manager_create_patch_integration.py`
- `tests/patch_manager/test_patch_manager_id_availability.py` (tags)
- `tests/patch_manager/test_patch_manager_remote_validation.py`
- `tests/patch_manager/test_patch_manager_directory_creation.py`
- Tous les tests utilisent `mock_hgit_complete` pour cohérence

## Implementation Notes

**Key improvements documented:**

1. **Atomic workflow**: All operations are transactional with proper rollback
2. **Tag-first strategy**: Prevents race conditions between developers
3. **Commit directory**: Patches/ directory is committed before tag creation
4. **Retry mechanism**: 3 automatic retries for branch push with exponential backoff
5. **Clear guarantees**: Tag push = point of no return, reservation complete

**Race condition prevention explained:**
- Old approach: branch push first → window for conflicts
- New approach: tag push first → atomic reservation, no conflicts possible

**Rollback behavior clarified:**
- Before tag push: full rollback (clean state)
- After tag push: no rollback (reservation complete, manual branch push if needed)
**Create patch branch:**

1. **Create patch from production**
   ```bash
   git checkout ho-prod  # Ensure we're on main branch
   half_orm dev create-patch "456"  # Check ticket 456 on github or gitlab
   ```
### Commande `apply-patch`
**Status :** ✅ Fonctionnelle et testée (217 tests passent, 1 skip)

**Implémentation complète :**

**Fonctionnalités principales :**
- ✅ Détection automatique patch depuis branche `ho-patch/*`
- ✅ Restauration DB depuis `model/schema.sql` (état production)
- ✅ **Support contexte de release (RC + stage)**
- ✅ Application patches en séquence : RC1 → RC2 → ... → stage → patch courant
- ✅ Ordre préservé si patch dans release
- ✅ Génération code Python via `modules.generate()`
- ✅ Rollback automatique sur erreur
- ✅ Messages CLI détaillés

**Architecture release context :**
```python
# ReleaseManager - Nouvelles méthodes
get_next_release_version()          # Détecte prochaine release (patch > minor > major)
get_rc_files(version)                # Liste RC files triés par numéro
read_release_patches(filename)       # Lit patch IDs depuis fichier release
get_all_release_context_patches()   # Séquence complète (RC1 + RC2 + ... + stage)

# PatchManager - Workflow modifié
apply_patch_complete_workflow(patch_id):
    1. Restore DB depuis model/schema.sql
    2. Récupérer contexte release (get_all_release_context_patches)
    3. Appliquer patches en ordre:
       - Si patch courant dans release → appliqué dans l'ordre
       - Si patch courant hors release → appliqué à la fin
    4. Générer code Python
    5. Retourner rapport détaillé
```

**Workflow avec contexte de release :**
```bash
# Scénario 1: Patch dans release
# releases/1.3.6-rc1.txt: 123, 456
# releases/1.3.6-stage.txt: 789, 234
# Patch courant: 789

half_orm dev apply-patch
# Exécution:
# 1. Restore DB (1.3.5 depuis model/schema.sql)
# 2. Apply 123 (depuis rc1)
# 3. Apply 456 (depuis rc1)
# 4. Apply 789 ← Patch courant appliqué DANS L'ORDRE
# 5. Apply 234 (depuis stage)
# 6. Generate code

# Scénario 2: Patch hors release
# releases/1.3.6-stage.txt: 123, 456
# Patch courant: 999

half_orm dev apply-patch
# Exécution:
# 1. Restore DB (1.3.5)
# 2. Apply 123 (depuis stage)
# 3. Apply 456 (depuis stage)
# 4. Apply 999 ← Patch courant appliqué À LA FIN
# 5. Generate code

# Scénario 3: Aucun contexte de release
half_orm dev apply-patch
# Exécution:
# 1. Restore DB (1.3.5)
# 2. Apply patch courant uniquement
# 3. Generate code
# → Backward compatibility préservée
```

**Structure de retour modifiée :**
```python
{
    'patch_id': str,                    # ID du patch courant
    'release_patches': List[str],       # Patches de release (sans patch courant)
    'applied_release_files': List[str], # Fichiers appliqués depuis release
    'applied_current_files': List[str], # Fichiers appliqués du patch courant
    'patch_was_in_release': bool,       # True si patch dans release
    'generated_files': List[str],       # Fichiers Python générés
    'status': str,                      # 'success' ou 'failed'
    'error': Optional[str]              # Message d'erreur si échec
}
```

**Gestion des erreurs et rollback :**
- ✅ Rollback automatique sur échec restauration DB
- ✅ Rollback automatique sur échec application patch
- ✅ Rollback automatique sur échec génération code
- ✅ Préservation erreur originale (rollback ne masque pas l'erreur)
- ✅ Suppression erreurs rollback (évite confusion)
- ✅ Validation pré-exécution (patch existe, schema.sql présent)

**Tests unitaires (217 passed, 1 skipped) :**

**1. Release context workflow (19 tests) :**
- `test_patch_manager_apply_patch_complet_workflow.py`
  - Tests `ReleaseManager.get_all_release_context_patches()`
  - Pas de release (backward compatibility)
  - Patch dans release (ordre préservé)
  - Patch hors release (appliqué à la fin)
  - Séquence RC + stage
  - Gestion commentaires et lignes vides
  - Préférence patch > minor > major

**2. Validation scenarios (7 tests + 1 skip) :**
- `test_patch_manager_apply_patch_validation.py`
  - Patch inexistant
  - Patch invalide (file au lieu de directory)
  - Schema.sql manquant
  - Patch vide (0 fichiers SQL/Python)
  - Patch avec fichiers non-exécutables uniquement
  - Patch avec mix fichiers valides/invalides
  - Schema.sql non-lisible (skip - dépend plateforme)

**3. Rollback scenarios (9 tests) :**
- `test_patch_manager_apply_patch_rollback.py`
  - Échec dropdb, createdb, psql
  - Échec application patch
  - Échec génération code
  - Préservation erreur originale
  - Suppression erreurs rollback
  - Rollback sur toute exception
  - Comportement avec release context
  - Validation des erreurs (sans rollback inutile)

**Implementation Notes :**

**1. Release Context Integration**
- Détection automatique de la prochaine release (patch → minor → major)
- Support RC incrémentaux (rc1 = patches initiaux, rc2 = nouveaux patches uniquement)
- Pas de déduplication nécessaire (chaque RC est incrémental par design)
- Application séquentielle stricte : RC1 → RC2 → ... → stage

**2. Ordre d'application préservé**
- Si patch courant dans release : appliqué dans l'ordre exact de la release
- Si patch courant hors release : appliqué après tous les patches de release
- Garantit cohérence entre tests développement et déploiement production

**3. Backward Compatibility**
- Comportement actuel préservé si aucun contexte de release
- Pas d'impact sur projets existants sans releases/
- Structure de retour étendue (pas cassée)

**4. Breaking Changes**
- `apply_patch_complete_workflow()` return structure modifiée :
  - ❌ Supprimé : `'applied_files'`
  - ✅ Ajouté : `'release_patches'`, `'applied_release_files'`,
    `'applied_current_files'`, `'patch_was_in_release'`
- CLI mis à jour pour nouvelle structure
- Tests d'intégration mis à jour

**5. Edge Cases Gérés**
- ✅ Aucun fichier de release
- ✅ Fichier release vide
- ✅ Patch courant en première/dernière position de release
- ✅ Commentaires et lignes vides dans fichiers release
- ✅ Multiples RC pour même version
- ✅ Mix RC + stage

**Prochaines étapes :**
- [ ] Implémentation `add-to-release` (ajout patch à stage)
- [ ] Tests avec vraies bases de données (intégration)
- [ ] Documentation workflow complet avec release context

### Commande `add-to-release`
**Status :** ✅ Fonctionnelle et testée (tests complets)

**Implémentation complète :**

**Méthodes ReleaseManager :**
1. ✅ `add_patch_to_release()` - Workflow complet avec lock distribué
2. ✅ `_detect_target_stage_file()` - Détection auto stage file (ou explicit)
3. ✅ `_apply_patch_change_to_stage_file()` - Ajout patch au fichier stage
4. ✅ `_run_validation_tests()` - Exécution pytest tests/
5. ✅ `_get_active_patch_branches()` - Liste branches patch actives
6. ✅ `_send_rebase_notifications()` - Notifications aux autres branches
7. ✅ `_create_notification_commit()` - Commit vide avec message

**CLI (half_orm_dev/cli/commands/add_to_release.py) :**
- ✅ Commande `half_orm dev add-to-release <patch_id>`
- ✅ Option `--to-version` pour sélection explicite
- ✅ Messages d'aide et next steps
- ✅ Gestion erreurs avec cleanup

**Fonctionnalités principales :**

**1. Lock distribué pour sécurité concurrentielle**
```bash
# Acquisition lock atomique via Git tag
LOCK_TAG="lock-ho-prod-$(date -u +%s%3N)"
git tag $LOCK_TAG && git push origin $LOCK_TAG

# Timeout 30 minutes avec détection staleness
# Lock toujours releasé (finally block) même sur erreur
```

**2. Workflow complet avec validation sur branche temporaire**
```bash
# Workflow en 17 étapes atomiques
1. Validations pré-lock (ho-prod, clean, patch exists)
2. Détection target stage (auto ou explicit)
3. Vérification patch pas déjà dans release
4. Acquisition lock distribué (atomic via tag)
5. Sync avec origin (fetch + pull si nécessaire)
6. Création branche temp-valid-{version}
7. Merge ALL patches déjà dans release (ho-release/X.Y.Z/*)
8. Merge nouveau patch (ho-patch/{patch_id})
9. Ajout patch au stage file + commit sur temp
10. Exécution tests validation (pytest tests/)
11. Si échec → cleanup + release lock + exit
12. Si succès → retour ho-prod + delete temp
13. Ajout patch au stage file sur ho-prod + commit (metadata only)
14. Push ho-prod vers origin
15. Notifications resync autres branches patch (stage mutable)
16. Archivage branche → ho-release/{version}/{patch_id}
17. Release lock (finally)

Note: Le code du patch n'est PAS mergé dans ho-prod à cette étape.
Le merge du code sera effectué lors du promote-to rc (release immuable).
```

**3. Gestion du code vs metadata**
- ✅ **Stage (mutable)** : ho-prod contient SEULEMENT `releases/*.txt` (metadata)
- ✅ **RC/Production (immuable)** : ho-prod contient code + metadata (merge effectué)
- ✅ Branche temp-valid = test intégration de TOUS les patches
- ✅ Code reste dans `ho-release/X.Y.Z/*` jusqu'au promote-to rc
- ✅ promote-to rc déclenche : merge code → ho-prod + notifications rebase

**Cycle de vie du code dans ho-prod :**
```bash
# Phase 1: add-to-release (stage mutable)
releases/1.3.6-stage.txt: "456-user-auth"  # Metadata seulement
ho-release/1.3.6/456-user-auth             # Code archivé ici

# Phase 2: promote-to rc (release immuable)
git mv releases/1.3.6-stage.txt releases/1.3.6-rc1.txt
git merge ho-release/1.3.6/456-user-auth   # CODE arrive dans ho-prod
git branch -D ho-patch/*                    # Cleanup branches dev

# Phase 3: branches actives rebasent
[ho] Resync notification: 1.3.6-rc1 promoted (REBASE REQUIRED)
# Développeurs font: git rebase ho-prod
```

**4. Validations robustes**
```python
# Pré-lock (exit early sans lock si échec)
- Branch = ho-prod
- Repository clean
- Patch exists (Patches/{patch_id}/)
- ho-patch/{patch_id} branch exists

# Post-lock (release lock en finally)
- ho-prod synced with origin (auto-pull if behind)
- Patch not already in release
- Tests pass on temp branch
```

**5. Archivage automatique**
```bash
# Après succès, branche archivée automatiquement
ho-patch/456-user-auth → ho-release/1.3.6/456-user-auth

# Suppression branche remote originale
git push origin --delete ho-patch/456-user-auth
```

**6. Notifications de resync**
```bash
# Notifications envoyées à toutes les branches patch actives
# Format: commit --allow-empty avec message structuré

[ho] Resync notification: 456-user-auth added to release 1.3.6-stage

Patch 456-user-auth has been integrated into 1.3.6-stage.
This is a stage release (mutable) - no immediate action required.

The code will be merged to ho-prod when the stage is promoted to RC.
At that point, active patch branches should rebase to include the changes.
```

**Tests unitaires (tous passent) :**

**1. Workflow complet :**
- `test_released_manager_add_patch_to_release.py`
  - Workflow succès complet avec lock
  - Échec acquisition lock (exit early)
  - Échec tests validation (cleanup + rollback)
  - Échec push (lock released)
  - Lock released sur erreur inattendue (finally)
  - Multiples stages (--to-version requis)

**2. Validations pré-lock :**
- `test_released_manager_add_to_release_validations.py`
  - Not on ho-prod branch
  - Repository not clean
  - Patch directory not exists
  - Patch branch not exists
  - Patch already in release

**3. Sync avec origin :**
- `test_released_manager_add_patch_to_release.py`
  - ho-prod behind → auto-pull
  - ho-prod diverged → error
  - ho-prod synced → continue

**4. Manipulation fichiers release :**
- `test_released_manager_add_to_release_helpers_branches_file.py`
  - Append to existing file
  - Append to empty file
  - Create file if not exists
  - Preserve existing content
  - Handle special chars in patch IDs
  - Proper newline handling
  - Error on permission denied

**5. Détection target stage :**
- `test_released_manager_add_to_release_helpers_detect_target.py`
  - Single stage → auto-detect
  - Multiple stages + explicit → use explicit
  - Multiple stages sans explicit → error
  - No stage files → error

**6. Notifications :**
- `test_released_manager_add_to_release_helpers_notifications.py`
  - Send to active branches
  - Skip archived branches
  - No notifications if no active
  - Commit format correct
  - Error handling

**7. Validation tests runner :**
- `test_released_manager_add_to_release_run_validation.py`
  - Tests pass → continue
  - Tests fail → error with output
  - Pytest command format
  - Working directory set
  - Stdout/stderr captured

**Edge Cases gérés :**
- ✅ Pas de stage file existant
- ✅ Multiples stage files (nécessite --to-version)
- ✅ Patch déjà dans release (erreur avant lock)
- ✅ Branches archivées ignorées (notifications)
- ✅ Lock stale (>30 min) → auto-cleanup et retry
- ✅ ho-prod diverged → erreur explicite
- ✅ Tests failure → rollback complet

**Structure de retour :**
```python
{
    'status': 'success',
    'patch_id': '456-user-auth',
    'target_version': '1.3.6',
    'stage_file': '1.3.6-stage.txt',
    'commit_sha': 'abc123def456...',
    'archived_branch': 'ho-release/1.3.6/456-user-auth',
    'notifications_sent': ['ho-patch/789-security'],
    'patches_in_release': ['123-initial', '456-user-auth']
}
```

**Usage :**
```bash
# Auto-detect stage (si une seule existe)
half_orm dev add-to-release "456-user-auth"

# Explicit version (si multiples stages)
half_orm dev add-to-release "456" --to-version="1.3.6"

# Output:
# ✓ Patch 456-user-auth added to release 1.3.6-stage
# ✓ Tests passed on temporary validation branch
# ✓ Committed to ho-prod: abc123de
# ✓ Branch archived: ho-release/1.3.6/456-user-auth
# ✓ Notified 2 active patch branches
#
# 📦 Release 1.3.6-stage now contains:
#    123-initial
#  → 456-user-auth
#    789-security
```

**Garanties transactionnelles :**
- Échec avant lock → Exit sans modification
- Lock acquis → Toujours released (finally)
- Échec validation → Cleanup temp branch + lock released
- Succès validation → Commit ho-prod + archivage + notifications

**Prévention race conditions :**
- Lock via Git tag (atomique)
- Premier à acquérir lock = seul autorisé
- Autres add-to-release bloqués jusqu'à release
- Opérations sur ho-patch/* toujours possibles

**Prochaines étapes :**
- [ ] Implémentation `promote-to rc` (promotion stage → rc)
- [ ] Tests avec vraies bases de données (intégration)
- [ ] Documentation workflow complet release

### Commande `promote-to rc`
**Status :** ✅ Fonctionnelle et testée (tests complets)

**Implémentation complète :**

**Méthodes ReleaseManager :**
2. ✅ `promote_to(target)` - Workflow unifié pour RC et production
3. ✅ `_detect_stage_to_promote()` - Détection du plus petit stage à promouvoir
4. ✅ `_validate_single_active_rc(version)` - Validation règle RC unique actif
5. ✅ `_determine_rc_number(version)` - Calcul du prochain numéro RC
6. ✅ `_merge_archived_patches_to_ho_prod()` - Merge code des patches archivés
7. ✅ `_cleanup_patch_branches()` - Suppression branches ho-patch/* après promotion
8. ✅ `_send_rebase_notifications()` - Notifications merge aux branches actives (WIP multi-target)

**CLI (half_orm_dev/cli/commands/promote_to.py) :**
- ✅ Commande `half_orm dev promote-to`
- ✅ Affichage détaillé : version, RC number, patches mergés, branches supprimées, notifications
- ✅ Messages next steps
- ✅ Gestion erreurs avec cleanup

**Fonctionnalités principales :**

**1. Lock distribué et workflow atomique**
```bash
# Workflow en 12 étapes atomiques
1. Validations pré-lock (ho-prod, clean)
2. Détection smallest stage (promotion séquentielle)
3. Validation single active RC rule
4. Acquisition lock distribué (atomic via tag)
5. Sync avec origin (fetch + pull si nécessaire)
6. Merge patches archivés → ho-prod (CODE MERGE CRITIQUE)
7. Rename stage file → RC file (git mv)
8. Commit + push promotion
9. Send rebase notifications to active branches
10. Cleanup patch branches (suppression ho-patch/*)
11. Release lock (finally block)
12. Return result dict

Note: À cette étape, le CODE est mergé dans ho-prod.
Les développeurs doivent merger ho-prod dans leurs branches actives.
```

**2. Règle Single Active RC**
```bash
# Un seul RC actif à la fois pour éviter confusion
# Bloque promotion si RC d'une version différente existe

# Exemple de blocage :
releases/1.3.5-rc1.txt existe
$ half_orm dev promote-to rc  # Voulant promouvoir 1.4.0-stage
❌ Error: Active RC exists: 1.3.5-rc1
   Must deploy 1.3.5-rc1 to production before promoting other versions.

# Promotion autorisée seulement si :
- Aucun RC actif (premier RC pour cette version)
- Ou RC de la MÊME version (incrémental rc2, rc3, etc.)
```

**3. RC incrémentaux**
```bash
# Support RC multiples pour même version
releases/1.3.5-stage.txt  → promote → 1.3.5-rc1.txt
# ... tests business, corrections ...
releases/1.3.5-stage.txt  → promote → 1.3.5-rc2.txt
# ... plus de tests ...
releases/1.3.5-stage.txt  → promote → 1.3.5-rc3.txt

# Chaque RC est incrémental (nouveaux patches uniquement)
# Numéro RC calculé automatiquement (max existant + 1)
```

**4. Merge code dans ho-prod**
```bash
# DIFFÉRENCE CRITIQUE avec add-to-release :
# add-to-release : metadata seulement (releases/*.txt)
# promote-to rc  : metadata + CODE

# Exemple :
releases/1.3.5-stage.txt contient : 456-user-auth, 789-security

$ half_orm dev promote-to rc

# Actions Git effectuées :
git merge ho-release/1.3.5/456-user-auth  # CODE mergé
git merge ho-release/1.3.5/789-security   # CODE mergé
git mv releases/1.3.5-stage.txt releases/1.3.5-rc1.txt
git commit -m "Promote 1.3.5-stage to 1.3.5-rc1"
git push

# Résultat : ho-prod contient maintenant le CODE des patches
```

**5. Cleanup automatique des branches**
```bash
# Après promotion, branches patch supprimées automatiquement
# (le code est maintenant dans ho-prod)

# Avant promote-to rc :
ho-patch/456-user-auth ✅ existe
ho-patch/789-security  ✅ existe

# Après promote-to rc :
ho-patch/456-user-auth ❌ supprimée (locale + remote)
ho-patch/789-security  ❌ supprimée (locale + remote)

# Branches archivées préservées :
ho-release/1.3.5/456-user-auth ✅ reste
ho-release/1.3.5/789-security  ✅ reste
```

**6. Notifications rebase/merge (WIP multi-target)**
```bash
# Notifications envoyées à TOUTES branches actives restantes
# Format : commit --allow-empty avec instructions merge

[ho] 1.3.5-rc1 promoted (MERGE REQUIRED)

Version 1.3.5-rc1 has been promoted with code merged to ho-prod.
Active patch branches MUST merge these changes.

Action required (branches are shared):
  git checkout ho-patch/999-reports
  git pull  # Get this notification
  git merge ho-prod
  # Resolve conflicts if any
  git push

Status: Action required (merge from ho-prod)

# Note WIP : Actuellement supporte ['alpha', 'beta', 'rc', 'prod']
# Mais validation promote_to() limite à ['rc', 'prod']
# Support alpha/beta complet à implémenter
```

**Tests unitaires (tous passent) :**

**1. Workflow complet :**
- `test_release_manager_promote_to_rc.py`
  - Workflow succès complet avec lock
  - Code merge effectué (branches archivées → ho-prod)
  - Stage renamed to rc1
  - RC number increment (rc1 → rc2 → rc3)
  - Branches cleanup après promotion
  - Notifications envoyées
  - Lock released sur erreur

**2. Détection stage :**
- `test_release_manager_promote_to_rc_detect_stage.py`
  - Single stage → auto-detect
  - Multiple stages → detect smallest version
  - No stage → error
  - Version parsing correct

**3. Validation Single Active RC :**
- `test_release_manager_promote_to_rc_validate_rc.py`
  - No active RC → allow promotion
  - Same version RC → allow (incremental)
  - Different version RC → block
  - Error message includes blocking RC version

**4. Numérotation RC :**
- `test_release_manager_promote_to_rc_rc_number.py`
  - First RC → rc1
  - Incremental → rc2, rc3, rc4...
  - Ignore other versions
  - Handle gaps in numbering
  - Support double-digit RC numbers

**5. Merge patches archivés :**
- `test_release_manager_promote_to_rc_merge_patches.py`
  - Merge all archived branches
  - Multiple patches merged sequentially
  - Empty stage → no merges
  - Error handling on merge conflicts

**6. Cleanup branches :**
- `test_release_manager_promote_to_rc_cleanup_branches.py`
  - Delete all ho-patch/* branches
  - Delete local + remote
  - Best effort (continue on errors)
  - Empty stage → no cleanup

**7. Notifications rebase :**
- `test_release_manager_promote_to_rc_notifications.py`
  - Send to all active patch branches
  - Message format correct (rc number, instructions)
  - Return to ho-prod after notifications
  - Continue on notification errors
  - Strip origin/ prefix from branch names
  - Ignore non-patch branches

**8. Tests d'intégration CLI :**
- `test_cli_integration_promote_to_rc.py`
  - RC file created from stage
  - Same patches content
  - Commit on ho-prod
  - RC file in commit
  - Branch deleted after promotion
  - Incremental RC (rc1 → rc2)

**Edge Cases gérés :**
- ✅ Pas de stage file → erreur explicite
- ✅ Multiples stages → détection smallest version
- ✅ RC actif différente version → blocage avec message
- ✅ Merge conflicts → erreur avec instructions
- ✅ Lock stale (>30 min) → auto-cleanup et retry
- ✅ ho-prod diverged → erreur explicite
- ✅ Empty stage → promotion autorisée (rc vide)
- ✅ Branch cleanup failures → continue (best effort)
- ✅ Notification failures → continue (non-blocking)

**Structure de retour :**
```python
{
    'status': 'success',
    'version': '1.3.5',
    'from_file': '1.3.5-stage.txt',
    'to_file': '1.3.5-rc1.txt',
    'rc_number': 1,
    'patches_merged': ['456-user-auth', '789-security'],
    'branches_deleted': ['ho-patch/456-user-auth', 'ho-patch/789-security'],
    'commit_sha': 'abc123def456...',
    'notifications_sent': ['ho-patch/999-reports'],
    'code_merged': True,
    'lock_tag': 'lock-ho-prod-1704123456789'
}
```

**Usage :**
```bash
# Promouvoir le plus petit stage
half_orm dev promote-to rc

# Output:
# ✓ Success!
# Promoted: 1.3.5-stage.txt → 1.3.5-rc1.txt
# Version: 1.3.5
# RC number: 1
#
# ✓ Merged 2 patches into ho-prod:
#   • 456-user-auth
#   • 789-security
#
# ✓ Deleted 2 patch branches
#
# ✓ Notified 1 active patch branches:
#   • ho-patch/999-reports
#
# Commit: abc123de
# Lock: lock-ho-prod-1704123456789
#
# 📝 Next steps:
#   1. Test RC: half_orm dev apply-release 1.3.5-rc1
#   2. If tests pass: half_orm dev promote-to prod
#   3. If issues: Fix patches and create 1.3.5-rc2
```

**Garanties transactionnelles :**
- Échec avant lock → Exit sans modification
- Lock acquis → Toujours released (finally)
- Merge conflicts → Cleanup + lock released
- Succès → Code dans ho-prod + branches supprimées + notifications

**Prévention race conditions :**
- Lock via Git tag (atomique)
- Single active RC rule (sequential deployments)
- Premier à acquérir lock = seul autorisé

**Breaking Changes par rapport à add-to-release :**
- ✅ `add-to-release` : pas de notifications (test sur branche temp)
- ✅ `promote-to rc` : notifications envoyées (code mergé dans ho-prod)
- ✅ Méthode `_send_resync_notifications()` supprimée
- ✅ Méthode `_send_rebase_notifications()` avec signature généralisée
- ✅ Support multi-target WIP : ['alpha', 'beta', 'rc', 'prod']

**Work In Progress (WIP) :**
- ⏸️ Support alpha/beta dans `_send_rebase_notifications()` implémenté
- ⏸️ Support alpha/beta dans `promote_to()` validation pas encore implémenté
- ⏸️ Pour activer alpha/beta : modifier ligne 1375 `if target not in ('rc', 'prod')`

**Prochaines étapes :**
- [ ] Finaliser support multi-target (alpha/beta)
- [ ] Implémentation `promote-to prod`
- [ ] Tests avec vraies bases de données (intégration)
- [ ] Documentation workflow complet release

---

## 🚧 En cours d'implémentation

### Commandes à implémenter (v0.16.0)

**1. `promote-to prod`**
- ⏸️ Promotion rc → production
- ⏸️ Restauration DB et application tous patches
- ⏸️ Génération schema-X.Y.Z.sql + metadata-X.Y.Z.sql
- ⏸️ Mise à jour symlink schema.sql
- ⏸️ Tests unitaires
- ⏸️ Support stage vide (production sans patches)

**2. `deploy-to-prod`** (OBSOLÈTE - fonctionnalité intégrée dans promote-to prod)
- ❌ Cette commande séparée n'est plus nécessaire
- ✅ Fonctionnalité intégrée directement dans `promote-to prod`
- ✅ `promote-to prod` gère : application patches + génération schema + symlink

**3. Support multi-target complet** (WIP)
- ⏸️ Finaliser support alpha/beta dans `promote_to()`
- ⏸️ Validation target parameter : ['alpha', 'beta', 'rc', 'prod']
- ⏸️ Numérotation automatique pour alpha/beta
- ⏸️ Documentation workflow alpha/beta
- ✅ `_send_rebase_notifications()` déjà compatible multi-target

**Architecture actuelle :**
```python
# _send_rebase_notifications() - ✅ Prêt pour multi-target
def _send_rebase_notifications(version, release_type, rc_number=None):
    # Supporte : 'alpha', 'beta', 'rc', 'prod'
    # Génère messages appropriés pour chaque type
    pass

# promote_to() - ⏸️ À étendre pour multi-target
def promote_to(target):
    if target not in ('rc', 'prod'):  # ← Ligne à modifier
        raise ValueError(...)
    # Ajouter logique pour 'alpha', 'beta'
```

---

## 🔮 Améliorations futures (post-v0.16.0)

### Refactoring technique

**1. Classe `Config` (priorité basse)**
**Problèmes identifiés :**
- Variables de classe au lieu d'instance (bug si plusieurs Config)
- `Config.__file` en variable de classe
- Effets de bord dans `__init__` (sys.path.insert, auto-read)
- Setters avec auto-write (pas de contrôle granulaire)
- Champ `config_file` redondant

**Impact actuel :** Aucun
- Usage actuel : une seule Config par repo
- Cas d'usage multi-repo non envisagé
- Variables de classe fonctionnent pour usage mono-repo

**Recommandation :**
- Reporter indéfiniment (pas de besoin identifié)
- Garder trace pour référence future
- Pas de priorité pour refactoring

**2. Migration templates packaging**
- Remplacer `setup.py` + `Pipfile` par `pyproject.toml`
- Standard Python moderne (PEP 518, 621)
- Non-bloquant pour workflow actuel

**3. Tests d'intégration**
- Tests avec vraie base PostgreSQL
- Workflow complet `init-database` → `init-project` → `create-patch`
- Complément aux tests unitaires actuels

**4. Suppression CHANGELOG.py**
- Remplacé par système `releases/*.txt`
- À supprimer dans commits futurs
- Fait partie du legacy workflow

### Nouvelles fonctionnalités

**1. Commandes secondaires**
- `create-hotfix` - Correctifs urgents
- `rollback` - Retour arrière base de données
- `list-patches` - Liste patches disponibles
- `status` - État développement

**2. CLI avancé**
- Commandes adaptatives selon contexte (branche ho-prod vs ho-patch)
- Validation automatique avant commits
- Intégration CI/CD

**3. Tests manquants**
- **IMPORTANT** : Module `modules.py` n'a pas de tests unitaires
  - Fonctionnalités critiques (génération code Python, dataclasses, etc.)
  - Tests à créer avant toute modification du module
  - Risque de régression élevé sans couverture tests
- **IMPORTANT** : Module `hgit.py` n'a pas de tests unitaires complets
  - Méthodes Git critiques (init, commit, rebase, etc.)
  - Tests partiels existants (test_hgit_initialization.py, test_hgit_utilities.py) mais incomplets
  - Couverture actuelle ~40% (besoin de tests complets pour legacy methods et proxies)
  - Tests à créer avant modifications majeures

---

## 📊 Statistiques

**Tests :**
- Total : 297 tests (dernière exécution)
- Tous passent : ✅

**Couverture par module :**
- `database.py` : Complète (tests init-database)
- `repo.py` (init-project) : ~100% (méthodes init complètes)
- `patch_manager.py` : Complète
- `hgit.py` : ~40% (tests partiels, besoin de tests complets)

**Modules de tests :**
```
tests/
├── cli/
├── conftest.py                           (fixtures communes)
├── database/
│   ├── test_database_get_connection_params.py
│   ├── test_database_load_configuration.py
│   └── test_database_setup.py
├── hgit/
│   ├── test_hgit_initialization.py
│   └── test_hgit_utilities.py
├── patch/
│   └── test_patch_validator.py
├── patch_manager/
│   ├── test_patch_manager_directory_creation.py
│   ├── test_patch_manager_initialization.py
│   ├── test_patch_manager_patch_application.py
│   ├── test_patch_manager_structure_analysis.py
│   └── test_patch_manager_utilities.py
└── repo/
    ├── test_repo_init_configuration.py
    ├── test_repo_init_mode_detection.py
    ├── test_repo_init_structure.py
    ├── test_repo_init_validation.py
    ├── test_repo_initialization.py
    ├── test_repo_manager.py
    └── test_repo_singleton.py
```

**Convention de nommage :**
- Pattern : `tests/{module}/test_{module}_{feature}.py`
- Préfixe obligatoire pour éviter conflits pytest
- Appliqué systématiquement à tous les fichiers de tests

---

## 🎯 Décisions d'architecture

### Méthodologie TDD progressive
- Tests unitaires avec mocks (rapides, isolés)
- Tests d'intégration planifiés pour plus tard
- Découpage modules tests : ~150 lignes max
- Commit atomiques par fonctionnalité

### Séparation init-database / init-project
- Deux commandes distinctes (au lieu d'une seule `new`)
- Database d'abord, projet ensuite
- Permet réutilisation DB entre projets
- Mode détection automatique (métadonnées présentes)

### Git-centric workflow
- Branche principale : `ho-prod` (remplace `hop_main`)
- Branches patches : `ho-patch/<patch-name>`
- Releases : `releases/X.Y.Z-stage.txt` → rc → production
- Pas de skip de versions (séquentiel strict)
- Messages commit système : `[ho]` (remplace `[hop]`)

### Simplification via délégation (KISS)
- `_initialize_git_repository()` : Simple délégation à `HGit.init()`
- `_generate_python_package()` : Délégation à `modules.generate()`
- `_generate_template_files()` : Lecture templates + formatting
- Pas de duplication de logique
- Réutilisation code existant testé

### Ordre d'exécution critique (init-project)
```
1. Validation
2. Vérification DB
3. Détection mode
4. Création répertoire
5. Configuration (.hop/config)
6. Structure Git-centrique (Patches/, releases/)
7. Database instance (self.database = Database(self))
8. Génération package Python (nécessite database.model)
9. Génération templates (README, .gitignore, etc.)
10. Initialisation Git (commit tous les fichiers sur ho-prod)
```

**Points critiques :**
- Database doit être initialisé **avant** generate (accès model)
- Templates doivent être créés **avant** Git init (inclus dans commit initial)
- Git checkout ho-prod **avant** commit (commit sur bonne branche)

---

## 📝 Notes techniques

### Imports à surveiller
- `Model` doit être importé au niveau module (pas local) pour testabilité
- Mocks de `Model.has_relation()` plus simple que `get_relation_class()`

### Patterns utilisés
- Singleton pour `Repo` (une instance par base_dir)
- Factory pattern pour `Database` (class methods)
- Delegation pattern pour `Config` (write() délégué)
- Delegation pattern pour `HGit` (init() délégué)
- Delegation pattern pour `modules.generate()` (génération code)

### Conventions
- Tests : `@pytest.mark.skip(reason="...")` pour features non implémentées
- Commits : Retrait skip uniquement après implémentation validée
- Messages : Format structuré (feat/test/fix + description)
- Messages système Git : `[ho]` au lieu de `[hop]`
- Nommage fichiers tests : `tests/{module}/test_{module}_{feature}.py`
  - Évite conflits d'imports pytest entre sous-répertoires
  - Exemple : `tests/repo/test_repo_initialization.py`
  - Systématique : préfixe du répertoire dans chaque nom de fichier

### Pièges évités
- ❌ Ne pas initialiser `self.database` avant `_generate_python_package()`
- ❌ Ne pas créer templates après `_initialize_git_repository()`
- ❌ Ne pas faire commit avant `git checkout -b ho-prod`
- ❌ Ne pas avoir de noms de fichiers tests identiques dans différents répertoires
- ✅ Ordre séquentiel strict dans `init_git_centric_project()`
- ✅ Préfixer tous les fichiers tests avec le nom du module
- ✅ Convention `test_{module}_{feature}.py` systématique

---

## 🐛 Bugs connus

**Aucun bug bloquant actuellement.**

---

## 📚 Documentation

**À jour :**
- `docs/half_orm_dev.md` - Documentation utilisateur complète
- `docs/dev_log.md` - Journal de développement (ce fichier)
- `README.md` - Vue d'ensemble projet
- Docstrings méthodes (exemples inclus)

**À créer/mettre à jour :**
- Guide migration ancienne commande `new` → `init-project`
- Tutoriel workflow complet développeur
- Architecture decisions records (ADR)

---

## 🔗 Ressources

**Liens utiles :**
- halfORM core : https://github.com/half-orm/half-orm
- Documentation : https://half-orm.github.io/half-orm/dev/
- Issues : https://github.com/half-orm/half-orm/issues

---

---

**Dernière session (2025-10-27) :** Finalisation commande `promote-to rc` + refactoring notifications

**Travaux effectués :**

1. **Refactoring système de notifications**
   - ✅ Suppression `_send_resync_notifications()` (inutile après validation temp branch)
   - ✅ Renommage `_send_resync_notifications()` → `_send_rebase_notifications()`
   - ✅ Généralisation signature : support multi-target ['alpha', 'beta', 'rc', 'prod']
   - ✅ Simplification implémentation : utilisation directe de `get_remote_branches()`
   - ✅ Amélioration messages notifications avec instructions merge claires

2. **Correction tests promote-to rc**
   - ✅ Adaptation tests aux nouveaux mocks `get_remote_branches()`
   - ✅ Correction assertions sur format de messages (rc1, rc2, etc.)
   - ✅ Gestion erreurs notifications (best effort, continue on failure)
   - ✅ Vérification paramètres `commit()` avec kwargs

3. **Breaking changes documentés**
   - ✅ `add-to-release` : plus de notifications (validation sur temp branch suffit)
   - ✅ CLI mise à jour : suppression affichage notifications dans add-to-release
   - ✅ Retour `add_patch_to_release()` : champ `notifications_sent` supprimé

4. **Architecture améliorée**
   - ✅ Séparation claire : stage mutable (metadata) vs RC immuable (code+metadata)
   - ✅ Notifications uniquement quand code mergé dans ho-prod (promote-to rc/prod)
   - ✅ Code plus simple et maintenable (KISS!)

**État des tests :**
- ✅ 823 tests passent (release_manager + promote-to rc)
- ✅ 0 échecs
- ✅ 1 skip (attendu)

**Work In Progress noté :**
- ⏸️ Support alpha/beta dans `_send_rebase_notifications()` : implémenté
- ⏸️ Support alpha/beta dans `promote_to()` validation : à implémenter
- ⏸️ Documentation : ajout note WIP dans code

**Prochaine session :** Implémentation `promote-to prod`
- Restauration DB et application tous patches (rc1 + rc2 + stage)
- Génération schema-X.Y.Z.sql + metadata-X.Y.Z.sql
- Mise à jour symlink schema.sql → schema-X.Y.Z.sql
- Support production vide (pas de stage)
- Notifications envoyées avec `release_type='prod'`

---

**Refactoring commande unifiée `promote-to` (KISS)**

**Travaux effectués :**

### 🎯 Refactoring majeur : Unification des commandes de promotion

**Motivation KISS :**
- Élimination de la redondance (3 méthodes → 1 méthode)
- API plus cohérente (CLI `promote-to` → méthode `promote_to()`)
- Code plus simple et maintenable
- Meilleure extensibilité (ajout futurs targets alpha/beta)

**Changements d'architecture :**

1. **ReleaseManager - Simplification API**
   - ❌ Suppression : `promote_to_rc()` (wrapper redondant)
   - ❌ Suppression : `promote_to_prod()` (wrapper redondant)
   - ✅ Renommage : `_promote_release(target)` → `promote_to(target)` (méthode publique)
   - Résultat : Une seule méthode publique au lieu de trois

2. **CLI - Commande unifiée**
   - ❌ Suppression : `promote-to-rc` (commande séparée)
   - ❌ Suppression : `promote-to-prod` (stub, non implémentée)
   - ✅ Nouvelle commande : `promote-to <target>` avec argument obligatoire
   - Choices : `['rc', 'prod']` (extensible vers alpha/beta)

3. **Breaking Changes CLI**
   ```bash
   # Ancienne syntaxe
   half_orm dev promote-to-rc
   half_orm dev promote-to-prod

   # Nouvelle syntaxe
   half_orm dev promote-to rc
   half_orm dev promote-to prod
   ```

**Modifications de code :**

1. **half_orm_dev/release_manager.py**
   - Ligne ~1350 : `def _promote_release(target)` → `def promote_to(target)`
   - Suppression méthodes `promote_to_rc()` et `promote_to_prod()` (~20 lignes)
   - Aucun changement de logique métier (code identique)

2. **half_orm_dev/cli/commands/promote_to.py**
   - Renommé depuis `promote_to_rc.py` (git mv)
   - Ajout argument : `@click.argument('target', type=click.Choice(['rc', 'prod']))`
   - Appel direct : `repo.release_manager.promote_to(target)` (au lieu du wrapper)
   - Affichage adaptatif selon target (RC number vs production info)

3. **half_orm_dev/cli/commands/__init__.py**
   - Import : `from .promote_to import promote_to` (au lieu de promote_to_rc)
   - Registration : `'promote-to': promote_to` (au lieu de promote-to-rc/promote-to-prod)
   - Simplification `ALL_COMMANDS` dict (-2 entrées redondantes)

4. **Mise à jour documentation et exemples**
   - `docs/dev_log.md` : Toutes références `promote-to-rc` → `promote-to rc`
   - `cli/commands/add_to_release.py` : Next steps mis à jour
   - `cli/commands/prepare_release.py` : Next steps mis à jour
   - `docs/half_orm_dev.md` : Exemples d'usage actualisés

5. **Adaptation tests (massive mais mécanique)**
   - ~15 fichiers de tests modifiés
   - Tous les appels `release_mgr.promote_to_rc()` → `release_mgr.promote_to_rc()`
   - Tous les appels `release_mgr.promote_to_prod()` → `release_mgr.promote_to_prod()`
   - Commentaires et docstrings mis à jour
   - Fichiers concernés :
     - `test_release_manager_promote_to_rc.py`
     - `test_release_manager_promote_to_rc_*.py` (8 fichiers)
     - `test_release_manager_promote_create_stage.py`
     - `test_cli_integration_promote_to_rc.py`
     - Fixtures dans `conftest.py`

**Résultats et bénéfices :**

1. **Simplicité (KISS) :**
   - Code supprimé : ~40 lignes (wrappers + imports redondants)
   - API surface réduite : 1 méthode publique au lieu de 3
   - Moins de duplication = moins de bugs potentiels

2. **Cohérence :**
   - CLI `promote-to <target>` ↔ API `promote_to(target)` (nommage aligné)
   - Pattern uniforme pour futures extensions (alpha, beta)
   - Une seule source de vérité pour la logique de promotion

3. **Maintenabilité :**
   - Modifications futures : 1 méthode à changer au lieu de 3
   - Tests plus clairs : explicit target parameter
   - Documentation centralisée sur une seule méthode

4. **Extensibilité :**
   ```python
   # Facile d'ajouter de nouveaux targets
   @click.argument('target', type=click.Choice(['alpha', 'beta', 'rc', 'prod']))
   def promote_to(target: str):
       result = repo.release_manager.promote_to(target)

   # Dans release_manager.py, juste étendre la validation
   def promote_to(self, target: str):
       if target not in ('alpha', 'beta', 'rc', 'prod'):
           raise ValueError(...)
   ```

**Tests et validation :**
- ✅ 841 tests unitaires passent (release_manager + promote-to)
- ✅ Tests CLI d'intégration passent
- ✅ Aucune régression détectée
- ✅ Coverage maintenue (100% des branches testées)

**Messages de commit :**
```
refactor: unify promote commands into single promote-to with target argument

BREAKING CHANGE: Replace promote-to-rc and promote-to-prod commands with unified promote-to

- Rename _promote_release() → promote_to() (now public API)
- Remove wrapper methods promote_to_rc() and promote_to_prod()
- CLI: promote-to-rc → promote-to rc, promote-to-prod → promote-to prod
- Add mandatory 'target' argument with choices ['rc', 'prod']
- Update all command examples and documentation
- Adapt all tests to use promote_to(target='rc'|'prod')

Benefits:
- Simpler API: one method instead of three (KISS principle)
- More consistent: CLI command matches ReleaseManager method
- Less code: removed redundant wrapper methods
- Better extensibility: easy to add 'alpha', 'beta' targets later

All tests passing (841 tests).
```

**Impact utilisateurs :**
- Migration simple : chercher/remplacer `promote-to-rc` → `promote-to rc`
- Aucun changement de comportement (logique identique)
- Commandes plus cohérentes et prévisibles
- Documentation mise à jour avec nouveaux exemples

**Prochaines étapes :**
- [ ] Finaliser implémentation `promote-to prod` (restauration DB, schema dumps)
- [ ] Support multi-target complet (alpha, beta) si besoin métier
- [ ] Tests d'intégration avec vraies bases de données
- [ ] Documentation workflow complet stage → rc → prod

---