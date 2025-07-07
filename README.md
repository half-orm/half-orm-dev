# halfORM packager with Git-Centric Workflow (early alpha stage)

> **🚀 Git-Centric Workflow Now Available!**
>
> **half-orm-dev now features a modern Git-centric workflow** that enables parallel development, automatic conflict detection, and intelligent branch management.
>
> **New in this version:**
> - 🔄 **Parallel development** on multiple versions simultaneously
> - 🚀 **Immediate version reservation** to prevent conflicts
> - 🧠 **Intelligent rebase warnings** with actionable suggestions
> - 🌿 **Automatic maintenance branches** for long-term support
> - 🧹 **Smart cleanup** of merged and tagged branches
> - ✅ **100% backward compatibility** with existing workflows
>
> **Status**: Production-ready with comprehensive test coverage (147+ tests)

---

## 🌟 **What's New: Git-Centric Workflow**

half-orm-dev now supports modern Git workflows while maintaining full compatibility with existing projects.

### **Key Features**

#### **🔄 Parallel Development**
Multiple developers can work on different versions simultaneously:

```bash
# Developer A
half_orm dev prepare -l minor -m "Add user authentication"
# ✅ Creates and reserves hop_1.3.0 immediately

# Developer B (at the same time)
half_orm dev prepare -l minor -m "Add API endpoints"  
# ✅ Automatically creates hop_1.4.0 (no conflicts!)
```

#### **🚀 Immediate Version Reservation**
No more coordination overhead - versions are reserved instantly:

```bash
half_orm dev prepare -l patch -m "Fix critical bug"
# ✅ Creates hop_1.2.1 branch
# 🔒 Immediately pushes to origin to reserve version
# 👥 Team sees work in progress instantly
```

#### **🧠 Intelligent Rebase Warnings**
Get contextual warnings when branches need attention:

```bash
half_orm dev apply
# ⚠️  WARNING: hop_1.2.3 is behind remote
# 💡 Consider rebasing: git rebase origin/hop_1.2.3
#
# ⚠️  WARNING: hop_1.2.x has advanced  
# 💡 Consider rebasing against maintenance: git rebase hop_1.2.x
```

#### **🌿 Automatic Maintenance Branches**
Long-term support branches created automatically:

```bash
half_orm dev release  # Releasing 1.3.0
# ✅ Created maintenance branch: hop_1.3.x
# 🔒 Available for future patches on 1.3.x line
```

## 📋 **Installation & Setup**

### **Requirements**
- Python 3.8+
- PostgreSQL database
- Git repository (local or remote)

### **Installation**
```bash
pip install half_orm_dev
```

### **Quick Start**

#### **1. Create New Project (Full Workflow)**
```bash
half_orm dev new myproject --full
cd myproject
```

#### **2. Create New Project (Sync-Only)**
```bash
half_orm dev new myproject
# No HOP metadata tables, just code sync
```

## 🔄 **Development Workflow**

### **Modern Git-Centric Approach**

```bash
# 1. Prepare a new release (reserves version immediately)
half_orm dev prepare -l minor -m "Add new feature"
# Creates hop_1.3.0 and pushes to origin

# 2. Develop your feature
# Edit database schema, add migrations
# Code is automatically synchronized

# 3. Apply and test
half_orm dev apply
# Applies patches and updates Python code

# 4. Release when ready  
half_orm dev release
# Tags release and creates maintenance branch
```

### **Branch Strategy**

The new workflow uses Git Flow-inspired branching:

```
hop_main ──────────────── 1.3.0 ──────── 1.4.0
     │                    │              │
     │               hop_1.3.x ── 1.3.1 ─┤
     │                                   │  
hop_1.2.x ── 1.2.4 ── 1.2.5 ─────────────┘
```

- **`hop_main`**: Latest stable release
- **`hop_X.Y.Z`**: Development branches for specific versions  
- **`hop_X.Y.x`**: Maintenance branches for patch series

## 📁 **Project Structure**

After running `half_orm dev new myproject --full`:

```
myproject/
├── Backups/              # Database backups
├── myproject/            # Generated Python package
│   ├── __init__.py
│   ├── ho_dataclasses.py # Dataclass definitions
│   └── public/           # Schema modules
├── Patches/              # Database migrations
│   ├── pre/              # Pre-patch scripts
│   ├── post/             # Post-patch scripts  
│   └── X/Y/Z/           # Version-specific patches
├── .hop/                 # HOP configuration
├── README.md
├── setup.py
└── Pipfile
```

## ⚙️ **Command Reference**

### **Development Commands** (Full Mode)
```bash
# Prepare new release
half_orm dev prepare -l <level> -m "<message>"
# Levels: patch, minor, major

# Apply current release  
half_orm dev apply

# Release current version
half_orm dev release -p  # -p to push

# Undo last release
half_orm dev undo
```

### **Production Commands** (Full Mode)
```bash
# Apply pending releases
half_orm dev upgrade

# Restore to specific release
half_orm dev restore <version>
```

### **Sync Commands** (Both Modes)
```bash
# Synchronize Python code with database
half_orm dev sync-package
```

## 🔀 **Migration from Legacy Workflow**

### **Existing Projects**
Existing half-orm-dev projects continue to work without changes. New Git-centric features activate automatically when beneficial.

### **Gradual Adoption**
1. **Keep existing workflow** - everything works as before
2. **Start using `half_orm dev prepare`** - gets immediate version reservation
3. **Adopt parallel development** - multiple versions simultaneously
4. **Leverage maintenance branches** - long-term support capabilities

## 🧪 **Testing**

The project includes comprehensive test coverage:

```bash
# Run all tests
pytest

# Run specific test levels
cd tests
python ordered_test_runner.py 1  # Git foundations
python ordered_test_runner.py 2  # Branch classification  
python ordered_test_runner.py 3  # Conflict detection
python ordered_test_runner.py 4  # Git actions
python ordered_test_runner.py 5  # Advanced logic
python ordered_test_runner.py 6  # Workflow integration
```

## 🔧 **Configuration**

### **Database Connection**
Configure in `/etc/half_orm/myproject` or `~/.halform/myproject`:

```ini
[database]
name = myproject
user = username
password = password
host = localhost  
port = 5432
production = false
```

### **Git Configuration**
HOP automatically detects and configures Git remotes. For private repositories:

```bash
git remote add origin <your-repo-url>
# HOP will automatically configure the remote
```

## 🛡️ **Backward Compatibility**

### **Breaking Changes** (Minor Impact)
- `half_orm dev prepare` now pushes immediately (security improvement)
- New branch naming conventions (feature enhancement)
- Simplified CHANGELOG format (implementation detail)

### **Migration Support**
- Existing commands work unchanged
- Automatic detection of legacy vs. new workflow
- Migration script for CHANGELOG format conversion

## 🆘 **Troubleshooting**

### **Common Issues**

#### **Version Conflicts**
```bash
# Error: Version conflict! hop_1.2.3 already exists
# Solution: Another developer is working on this version
half_orm dev prepare -l patch -m "Different message"  # Creates 1.2.4
```

#### **Rebase Needed**
```bash
# Warning: hop_1.2.3 is behind remote
git fetch origin
git rebase origin/hop_1.2.3
```

#### **Cleanup Branches**
```bash
# Manual cleanup of old branches
half_orm dev upgrade  # In production - auto-cleanup
```

## 📚 **Documentation**

- **[Git-Centric Workflow Guide](docs/git-centric-workflow.md)** - Detailed workflow documentation
- **[Migration Guide](docs/migration-guide.md)** - Upgrading from legacy workflow
- **[Best Practices](docs/best-practices.md)** - Team collaboration patterns
- **[API Reference](docs/api-reference.md)** - Complete command reference

## 🤝 **Contributing**

We welcome contributions! The project uses a test-driven development approach:

1. **Write tests first** - All new features require comprehensive tests
2. **Progressive implementation** - Features are built level by level
3. **Backward compatibility** - Existing functionality must be preserved
4. **Documentation** - All changes require documentation updates

## 📄 **License**

This project is licensed under the GNU General Public License v3.0 - see the LICENSE file for details.

## 🙏 **Acknowledgments**

- Built on [halfORM](https://github.com/collorg/halfORM) - PostgreSQL to Python object mapper
- Inspired by Git Flow and modern Git workflows
- Test-driven development methodology

---

**Need Help?** 
- 📖 Check the [documentation](docs/)
- 🐛 Report [issues](https://github.com/half-orm/half-orm-dev/issues)  
- 💬 Join [discussions](https://github.com/half-orm/half-orm-dev/discussions)