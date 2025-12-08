# Analyse: Migration des fichiers releases de TXT vers TOML

## 1. État actuel du système

### 1.1 Format actuel: Deux fichiers TXT par release (développement)

Chaque release `X.Y.Z` **en développement** a deux fichiers dans `.hop/releases/`:
- `X.Y.Z-candidates.txt`: Liste des patches en développement
- `X.Y.Z-stage.txt`: Liste des patches intégrés (fermés)

**Format TXT:**
```
# X.Y.Z-candidates.txt
1-auth
2-api
3-bugfix

# X.Y.Z-stage.txt
1-auth
3-bugfix
```

### 1.2 Fichiers de release/production (NON concernés par ce refactoring)

Ces fichiers **restent inchangés** et conservent leur logique actuelle:
- `X.Y.Z-rc1.txt`, `X.Y.Z-rc2.txt`: Snapshots des release candidates
- `X.Y.Z.txt`: Snapshot de la version production finale
- `X.Y.Z-hotfix1.txt`: Snapshots des hotfixes

**Contenu** (liste simple de patches, pas de statut):
```
# X.Y.Z-rc1.txt
1-auth
2-api
3-bugfix
```

### 1.3 Problèmes identifiés (fichiers de développement uniquement)

1. **Duplication**: Un patch apparaît dans `candidates` puis dans `stage`
2. **Ordre différent**: Lors du `patch close`, le patch est:
   - Retiré de `candidates` (ligne supprimée)
   - Ajouté à la fin de `stage` (append)
   - Résultat: ordre différent entre les deux fichiers
3. **Source de vérité fragmentée**: Deux fichiers à maintenir synchronisés
4. **Pas de support pour insertion**: Impossible d'insérer un patch avant un autre

### 1.4 Fichiers concernés par le refactoring

**Code principal:**
- `half_orm_dev/release_manager.py`:
  - `new_release()`: Crée les fichiers vides (ligne 2463-2474)
  - `_generate_data_sql_file()`: Utilise l'ordre des patches (ligne 734) - **Ne touche que stage**
  - `get_all_release_context_patches()`: Collecte tous les patches

- `half_orm_dev/patch_manager.py`:
  - `_add_patch_to_candidates()`: Ajoute à candidates (ligne 2432)
  - `_move_patch_to_stage()`: Déplace de candidates vers stage (ligne 2570)
  - `_find_version_for_candidate()`: Cherche dans candidates (ligne 2507)
  - `_get_other_candidates()`: Liste autres candidates (ligne 2621)
  - `_commit_patch_to_candidates()`: Commit le fichier candidates (ligne 2467)

**Code NON concerné** (reste inchangé):
- Toute la logique de promotion vers RC (`promote_to_rc`)
- Toute la logique de promotion vers prod (`promote_to_prod`)
- Génération des fichiers `-rc*.txt` et `.txt`

**Tests:** Environ 10-15 fichiers de tests à adapter (seulement ceux testant patch add/close)

### 1.5 Opérations actuelles (développement)

**Création** (`release new`):
```python
# release_manager.py:2463-2474
candidates_file.write_text("", encoding='utf-8')
stage_file.write_text("", encoding='utf-8')
```

**Ajout** (`patch add`):
```python
# patch_manager.py:2460
with candidates_file.open('a', encoding='utf-8') as f:
    f.write(f"{patch_id}\n")
```

**Fermeture** (`patch close`):
```python
# patch_manager.py:2593-2608
# 1. Lire candidates
candidates = [line.strip() for line in candidates_content.split('\n')]
# 2. Retirer le patch
candidates.remove(patch_id)
# 3. Réécrire candidates
candidates_file.write_text('\n'.join(candidates) + '\n')
# 4. Ajouter à stage
with stage_file.open('a', encoding='utf-8') as f:
    f.write(f"{patch_id}\n")
```

**Lecture** (pour application):
```python
# patch_manager.py:1967-1973
content = stage_file.read_text(encoding='utf-8').strip()
staged_patches = [
    line.strip()
    for line in content.split('\n')
    if line.strip() and not line.strip().startswith('#')
]
```

## 2. Nouveau format TOML proposé

### 2.1 Structure du fichier

**Un seul fichier par release en développement:** `.hop/releases/X.Y.Z-patches.toml`

```toml
[patches]
"1-auth" = "candidate"
"2-api" = "candidate"
"3-bugfix" = "staged"
```

**Note importante:** Le nom `X.Y.Z-patches.toml` évite toute confusion avec:
- `X.Y.Z.txt` (version prod)
- `X.Y.Z-rc1.txt` (release candidates)

### 2.2 Avantages

1. **Un seul ordre**: Position dans le fichier = ordre d'application (conservé de bout en bout)
2. **État explicite**: `candidate` ou `staged` sur la même ligne
3. **Pas de duplication**: Un patch n'apparaît qu'une seule fois
4. **Facile à parser**: Format structuré avec bibliothèque Python `tomli`/`tomli_w`
5. **Support d'insertion**: Facile d'insérer une ligne avant une autre
6. **Portée limitée**: Ne touche pas à la logique de promotion RC/prod

### 2.3 Exemple de workflow

**Création release:**
```toml
[patches]
# Vide au départ
```

**Ajout patch 1-auth:**
```toml
[patches]
"1-auth" = "candidate"
```

**Ajout patch 2-api:**
```toml
[patches]
"1-auth" = "candidate"
"2-api" = "candidate"
```

**Ajout patch 3-bugfix AVANT 2-api** (`--before 2-api`):
```toml
[patches]
"1-auth" = "candidate"
"3-bugfix" = "candidate"  # Inséré avant 2-api
"2-api" = "candidate"
```

**Close patch 1-auth** (change juste le statut):
```toml
[patches]
"1-auth" = "staged"        # Juste le statut change, ordre préservé!
"3-bugfix" = "candidate"
"2-api" = "candidate"
```

**Promote to RC** (génère `X.Y.Z-rc1.txt` depuis patches.toml):
```
# X.Y.Z-rc1.txt (généré, format TXT inchangé)
1-auth
# Seuls les patches "staged" sont inclus
```

## 3. Plan d'implémentation

### 3.1 Nouvelles méthodes à créer

**Classe ReleaseFile** (nouveau module `half_orm_dev/release_file.py`):
```python
class ReleaseFile:
    """Manage TOML release files (X.Y.Z-patches.toml)."""

    def __init__(self, version: str, releases_dir: Path):
        self.version = version
        self.file_path = releases_dir / f"{version}-patches.toml"

    def create_empty(self) -> None:
        """Create empty TOML file."""

    def add_patch(self, patch_id: str, before: Optional[str] = None) -> None:
        """Add patch as candidate, optionally before another patch."""

    def move_to_staged(self, patch_id: str) -> None:
        """Change patch status from candidate to staged."""

    def get_patches(self, status: Optional[str] = None) -> List[str]:
        """Get patches (all, or filtered by status), in order."""

    def get_patch_status(self, patch_id: str) -> Optional[str]:
        """Get status of a specific patch."""

    def remove_patch(self, patch_id: str) -> None:
        """Remove a patch completely."""
```

### 3.2 Modifications des méthodes existantes

**release_manager.py:**
- `new_release()`: Créer `X.Y.Z-patches.toml` au lieu de `-candidates.txt` et `-stage.txt`
- `_generate_data_sql_file()`: Utiliser `ReleaseFile.get_patches(status="staged")`
- **PAS de changement** dans `promote_to_rc()` et `promote_to_prod()`

**patch_manager.py:**
- `_add_patch_to_candidates()`: Utiliser `ReleaseFile.add_patch()`
- `_move_patch_to_stage()`: Utiliser `ReleaseFile.move_to_staged()`
- `_find_version_for_candidate()`: Utiliser `ReleaseFile.get_patch_status()`
- `_get_other_candidates()`: Utiliser `ReleaseFile.get_patches(status="candidate")`

**CLI patch.py:**
- `add()`: Ajouter option `--before <patch_id>`

### 3.3 Migration automatique (0.17.1)

**Script de migration:** `half_orm_dev/migrations/0/17/1/01_txt_to_toml.py`

```python
def migrate(repo):
    """
    Convert release files from TXT to TOML format.

    For each X.Y.Z release in development:
    - Read X.Y.Z-candidates.txt
    - Read X.Y.Z-stage.txt
    - Create X.Y.Z-patches.toml with all patches in order:
      - candidates first (in their order)
      - staged second (in their order)
    - Delete old .txt files

    IMPORTANT: Does NOT touch RC or prod files (-rc*.txt, .txt)
    """
    releases_dir = repo.local_config.releases_dir

    # Find all candidates files
    candidates_files = list(releases_dir.glob("*-candidates.txt"))

    for candidates_file in candidates_files:
        version = candidates_file.stem.replace('-candidates', '')
        stage_file = releases_dir / f"{version}-stage.txt"

        # Read patches
        candidates = read_patches_from_file(candidates_file)
        staged = read_patches_from_file(stage_file) if stage_file.exists() else []

        # Create TOML
        toml_data = {"patches": {}}
        for patch_id in candidates:
            toml_data["patches"][patch_id] = "candidate"
        for patch_id in staged:
            toml_data["patches"][patch_id] = "staged"

        # Write TOML file
        toml_file = releases_dir / f"{version}-patches.toml"
        write_toml(toml_file, toml_data)

        # Delete old files
        candidates_file.unlink()
        if stage_file.exists():
            stage_file.unlink()
```

**Note:** L'ordre sera: tous les candidates d'abord, puis tous les staged.
C'est une limitation acceptable pour la migration initiale.

### 3.4 Gestion de l'ordre TOML

Python 3.7+ garantit l'ordre d'insertion des dicts. Pour lire/écrire en préservant l'ordre:

```python
import tomli  # Pour lire (Python <3.11)
import tomli_w  # Pour écrire

# Lecture
with open(file_path, 'rb') as f:
    data = tomli.load(f)  # dict ordonné

# Écriture (préserve l'ordre)
with open(file_path, 'wb') as f:
    tomli_w.dump(data, f)

# Insertion avant un élément
def insert_before(patches: dict, new_key: str, before_key: str, value: str):
    new_patches = {}
    for key, val in patches.items():
        if key == before_key:
            new_patches[new_key] = value
        new_patches[key] = val
    return new_patches
```

## 4. Tests à mettre à jour

**Fichiers de tests concernés** (environ 10-15):
- `test_patch_manager_*.py` (tests de patch add/close)
- `test_release_manager_integration_workflow.py` (si teste candidates/stage)
- Tests CLI de `patch add` et `patch close`

**Fichiers NON concernés**:
- Tests de promotion RC/prod (aucun changement)
- Tests de génération de fichiers RC/prod

**Stratégie:**
1. Créer des helpers de test pour le format TOML
2. Mettre à jour fixtures pour utiliser TOML
3. Adapter les assertions

## 5. Chronologie d'implémentation

1. ✅ Analyse approfondie du code existant
2. ⏳ Créer `release_file.py` avec classe `ReleaseFile`
3. ⏳ Ajouter dépendances `tomli` et `tomli_w` à `pyproject.toml`
4. ⏳ Créer migration `01_txt_to_toml.py`
5. ⏳ Modifier `release_manager.py` pour utiliser TOML (seulement `new_release`)
6. ⏳ Modifier `patch_manager.py` pour utiliser TOML
7. ⏳ Ajouter option `--before` à `patch add`
8. ⏳ Mettre à jour les tests concernés
9. ⏳ Tester la migration sur projet réel
10. ⏳ Documentation

## 6. Points d'attention

1. **Portée limitée**: Seuls les fichiers de développement (-candidates/-stage) sont concernés
2. **Logique RC/prod inchangée**: Toute la logique de promotion reste identique
3. **Backward compatibility**: La migration doit gérer les projets existants
4. **Ordre lors de la migration**: candidates d'abord, staged ensuite (acceptable)
5. **Atomicité**: Les opérations doivent rester atomiques (read → modify → write)
6. **Git operations**: Ajuster les commits pour référencer `.toml` au lieu de `.txt`
7. **Performance**: TOML parsing plus lent que TXT, mais négligeable vu la taille des fichiers

## 7. Avantages de cette approche limitée

1. ✅ **Risque minimal**: Logique de release/production intacte
2. ✅ **Tests limités**: Seulement patch add/close à tester
3. ✅ **Migration simple**: Conversion directe candidates+stage → patches
4. ✅ **Rollback facile**: Peut revenir en arrière si problème
5. ✅ **Valeur immédiate**: Résout le problème d'ordre dès le développement
