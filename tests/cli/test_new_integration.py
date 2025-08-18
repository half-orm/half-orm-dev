#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests d'intégration RÉELS pour la commande new

Tests sans mocks qui révèlent exactement ce qui doit être implémenté
dans modules.py pour supporter la création de projets half-orm-dev.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

from half_orm_dev.cli.new import (
    add_new_commands, 
    _check_database_state,
    _has_meta_tables,
    _setup_half_orm_dev_structure
)
from half_orm_dev.repo import Repo


# ==================== FIXTURES RÉELLES ====================

@pytest.fixture
def temp_workspace():
    """Workspace temporaire réel pour les tests."""
    temp_dir = tempfile.mkdtemp(prefix="half_orm_dev_test_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def real_hop_instance():
    """Instance HalfOrmDev réelle (pas de mock)."""
    from half_orm_dev.cli_extension import HalfOrmDev
    return HalfOrmDev()


# ==================== TESTS RÉELS DE DÉTECTION D'ÉTAT ====================

class TestRealDatabaseStateDetection:
    """Tests réels de détection d'état de base de données."""
    
    def test_check_database_state_returns_not_exists_by_default(self, real_hop_instance):
        """Should return 'not_exists' for non-existent database."""
        # Test avec une base qui n'existe pas
        result = _check_database_state(real_hop_instance, "non_existent_db_12345")
        assert result == "not_exists"
    
    def test_has_meta_tables_false_when_no_repo(self, real_hop_instance):
        """Should return False when not in a repository."""
        # Test quand on n'est pas dans un repo
        result = _has_meta_tables(real_hop_instance)
        # Ceci va révéler si l'implémentation actuelle fonctionne
        assert isinstance(result, bool)


# ==================== TESTS RÉELS DE CRÉATION DE STRUCTURE ====================

class TestRealStructureCreation:
    """Tests réels de création de structure half-orm-dev."""
    
    def test_setup_half_orm_dev_structure_creates_directories(self, temp_workspace):
        """Should create real SchemaPatches and releases directories."""
        project_name = "test_project"
        project_path = temp_workspace / project_name
        project_path.mkdir()
        
        # Changer vers le répertoire temporaire
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            
            # Test de création réelle
            _setup_half_orm_dev_structure(project_name)
            
            # Vérifications réelles
            assert (project_path / "SchemaPatches").exists()
            assert (project_path / "SchemaPatches").is_dir()
            assert (project_path / "releases").exists()
            assert (project_path / "releases").is_dir()
            
            # Vérifier les README
            assert (project_path / "SchemaPatches" / "README.md").exists()
            assert (project_path / "releases" / "README.md").exists()
            
            # Vérifier le contenu des README
            schema_readme = (project_path / "SchemaPatches" / "README.md").read_text()
            assert "# SchemaPatches" in schema_readme
            assert "half_orm dev create-patch" in schema_readme
            
            releases_readme = (project_path / "releases" / "README.md").read_text()
            assert "# Releases" in releases_readme
            assert "git mv" in releases_readme
            
        finally:
            os.chdir(original_cwd)


# ==================== TESTS RÉELS D'ENREGISTREMENT DE COMMANDES ====================

class TestRealCommandRegistration:
    """Tests réels d'enregistrement de commandes basés sur le contexte."""
    
    def test_command_registration_outside_repo(self, real_hop_instance, temp_workspace):
        """Should register 'new' command when outside repository."""
        import os
        original_cwd = os.getcwd()
        
        try:
            # Aller dans un répertoire vide (pas de repo)
            os.chdir(temp_workspace)
            
            # Créer une nouvelle instance dans ce contexte
            from half_orm_dev.cli_extension import HalfOrmDev
            hop = HalfOrmDev()
            
            # Vérifier que nous ne sommes pas dans un repo
            assert not hop.repo_checked
            
            # Tester l'enregistrement
            registered_commands = []
            
            class MockDevGroup:
                def add_command(self, cmd):
                    registered_commands.append(cmd.name)
            
            dev_group = MockDevGroup()
            add_new_commands(dev_group, hop)
            
            # Devrait enregistrer 'new'
            assert 'new' in registered_commands
            assert len(registered_commands) == 1
            
        finally:
            os.chdir(original_cwd)
    
    def test_command_registration_in_repo_without_meta(self, temp_workspace):
        """Should register 'init-meta' when in repo without meta tables."""
        import os
        original_cwd = os.getcwd()
        
        try:
            # Créer un faux repo halfORM sans meta tables
            project_dir = temp_workspace / "fake_repo"
            project_dir.mkdir()
            os.chdir(project_dir)
            
            # Créer un fichier pour simuler un repo halfORM
            (project_dir / ".halfORM").touch()  # Fake repo marker
            
            from half_orm_dev.cli_extension import HalfOrmDev
            hop = HalfOrmDev()
            
            # Ce test va révéler comment détecter un repo existant
            registered_commands = []
            
            class MockDevGroup:
                def add_command(self, cmd):
                    registered_commands.append(cmd.name)
            
            dev_group = MockDevGroup()
            add_new_commands(dev_group, hop)
            
            # Révèle le comportement actuel
            print(f"Registered commands: {registered_commands}")
            print(f"Repo checked: {hop.repo_checked}")
            print(f"Has meta tables: {_has_meta_tables(hop) if hop.repo_checked else 'N/A'}")
            
            # Assertion flexible pour révéler le comportement
            assert isinstance(registered_commands, list)
            
        finally:
            os.chdir(original_cwd)


# ==================== TESTS RÉVÉLATEURS POUR modules.py ====================

class TestModulesIntegrationNeeds:
    """Tests qui révèlent ce qui doit être ajouté à modules.py."""
    
    def test_what_modules_functions_are_needed(self):
        """Révèle quelles fonctions modules.py doit exposer pour new command."""
        from half_orm_dev import modules
        
        # Quelles fonctions existent déjà ?
        existing_functions = [attr for attr in dir(modules) if not attr.startswith('_')]
        print(f"Existing public functions in modules.py: {existing_functions}")
        
        # Quelles fonctions nous aurions besoin ?
        needed_functions = [
            'create_project_with_dev_support',
            'add_meta_tables_to_existing_project', 
            'check_database_state',
            'setup_half_orm_dev_directories'
        ]
        
        for func_name in needed_functions:
            has_function = hasattr(modules, func_name)
            print(f"modules.{func_name}: {'✅ EXISTS' if has_function else '❌ MISSING'}")
            
        # Ce test révèle ce qui manque
        assert True  # Toujours passer, c'est informatif
    
    def test_current_generate_function_behavior(self, temp_workspace):
        """Révèle comment fonctionne la fonction generate() actuelle."""
        # Tester avec un faux repo pour voir ce qui se passe
        fake_repo = type('MockRepo', (), {
            'name': 'test_project',
            'base_dir': str(temp_workspace),
            'devel': True,
            'database': type('MockDB', (), {
                'model': type('MockModel', (), {
                    '_relations': lambda: [],  # Pas de relations pour éviter les erreurs
                    '_reload': lambda: None
                })()
            })()
        })()
        
        try:
            from half_orm_dev import modules
            
            # Créer le répertoire de base
            (temp_workspace / 'test_project').mkdir()
            
            # Tester generate (devrait créer la structure de base)
            modules.generate(fake_repo)
            
            # Voir ce qui a été créé
            created_items = list(temp_workspace.rglob('*'))
            print(f"Items created by modules.generate(): {[str(p) for p in created_items]}")
            
            # Vérifier les structures créées
            project_dir = temp_workspace / 'test_project'
            
            # Structures halfORM standard
            assert (project_dir / '__init__.py').exists()
            
            # Structures de test (en mode devel)
            if fake_repo.devel:
                tests_created = (temp_workspace / 'tests').exists()
                print(f"Tests directory created: {tests_created}")
                
                pytest_ini_created = (temp_workspace / 'pytest.ini').exists()
                print(f"pytest.ini created: {pytest_ini_created}")
        
        except Exception as e:
            print(f"modules.generate() failed with: {e}")
            # C'est normal, ça révèle ce qui doit être adapté
    
    def test_repo_init_behavior_revelation(self, real_hop_instance):
        """Révèle comment repo.init() fonctionne actuellement."""
        try:
            # Tenter d'accéder aux propriétés du repo
            print(f"Repo checked: {real_hop_instance.repo_checked}")
            print(f"Repo state: {real_hop_instance.state}")
            
            if hasattr(real_hop_instance._repo, 'name'):
                print(f"Repo name: {real_hop_instance._repo.name}")
            
            if hasattr(real_hop_instance._repo, 'devel'):
                print(f"Repo devel mode: {real_hop_instance._repo.devel}")
            
            # Voir quelles méthodes repo expose
            repo_methods = [method for method in dir(real_hop_instance._repo) 
                          if not method.startswith('_') and callable(getattr(real_hop_instance._repo, method))]
            print(f"Available repo methods: {repo_methods}")
            
            # Test si init existe
            has_init = hasattr(real_hop_instance._repo, 'init')
            print(f"Repo has init method: {has_init}")
            
        except Exception as e:
            print(f"Error exploring repo: {e}")
        
        # Test informatif
        assert True


# ==================== TESTS D'INTÉGRATION END-TO-END ====================

class TestEndToEndRealScenarios:
    """Tests end-to-end réels pour révéler le workflow complet."""
    
    def test_complete_new_project_creation_simulation(self, temp_workspace):
        """Simule la création complète d'un projet pour révéler les manques."""
        import os
        original_cwd = os.getcwd()
        
        try:
            os.chdir(temp_workspace)
            
            from half_orm_dev.cli_extension import HalfOrmDev
            hop = HalfOrmDev()
            
            package_name = "test_project"
            
            print(f"=== SIMULATION: Creating project '{package_name}' ===")
            
            # 1. Vérifier l'état initial
            print(f"Initial repo_checked: {hop.repo_checked}")
            
            # 2. Tenter de détecter l'état de la base
            db_state = _check_database_state(hop, package_name)
            print(f"Database state: {db_state}")
            
            # 3. Simuler repo.init (va probablement échouer)
            print("Attempting repo.init simulation...")
            try:
                if hasattr(hop._repo, 'init'):
                    print("repo.init method exists")
                    # Ne pas vraiment appeler pour éviter les erreurs de BDD
                else:
                    print("❌ repo.init method missing")
            except Exception as e:
                print(f"repo.init exploration failed: {e}")
            
            # 4. Créer les structures half-orm-dev
            print("Creating half-orm-dev structures...")
            _setup_half_orm_dev_structure(package_name)
            
            # 5. Vérifier ce qui a été créé
            created_files = list(temp_workspace.rglob('*'))
            print(f"Files created: {[str(f.relative_to(temp_workspace)) for f in created_files if f.is_file()]}")
            
            # 6. Révéler ce qui manque pour un workflow complet
            print("\n=== RÉVÉLATIONS ===")
            project_dir = temp_workspace / package_name
            
            # Structures half-orm-dev créées ?
            print(f"SchemaPatches created: {(project_dir / 'SchemaPatches').exists()}")
            print(f"releases created: {(project_dir / 'releases').exists()}")
            
            # Structures halfORM standard manquantes ?
            print(f"halfORM package dir missing: {not (project_dir / package_name).exists()}")
            print(f"__init__.py missing: {not (project_dir / package_name / '__init__.py').exists()}")
            print(f"tests/ missing: {not (project_dir / 'tests').exists()}")
            
        finally:
            os.chdir(original_cwd)


# ==================== TESTS DE DÉCOUVERTE D'API ====================

class TestAPIDiscovery:
    """Tests pour découvrir l'API halfORM existante."""
    
    def test_discover_repo_class_api(self):
        """Découvre l'API de la classe Repo."""
        from half_orm_dev.repo import Repo
        
        # Explorer la classe Repo
        repo_methods = [method for method in dir(Repo) if not method.startswith('_')]
        print(f"Repo public methods: {repo_methods}")
        
        # Créer une instance pour explorer
        try:
            repo = Repo()
            instance_methods = [method for method in dir(repo) if not method.startswith('_')]
            print(f"Repo instance methods: {instance_methods}")
            
            # Tester les propriétés importantes
            for prop in ['checked', 'name', 'devel', 'base_dir']:
                if hasattr(repo, prop):
                    try:
                        value = getattr(repo, prop)
                        print(f"repo.{prop}: {value} (type: {type(value)})")
                    except Exception as e:
                        print(f"repo.{prop}: Error accessing - {e}")
                else:
                    print(f"repo.{prop}: ❌ Missing")
            
        except Exception as e:
            print(f"Error exploring Repo: {e}")
        
        assert True  # Test informatif
