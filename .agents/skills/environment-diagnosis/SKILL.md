---
name: environment-diagnosis
description: Diagnose missing or broken project development tools without rebuilding the entire environment.
---

# Environment diagnosis

1. Inspect the current mise state:

```bash
mise current
mise list
```

2. Inspect runtime versions:

```bash
rustc --version
cargo --version
node --version
pnpm --version
uv --version
python --version
go version
```

3. For Rust component failures:

```bash
rustup show
rustup component list --installed
```

4. If a component declared by the repository is missing, repair it using:

```bash
mise install
```

5. Do not reinstall the entire environment unless targeted repair fails.

6. Never change language versions merely to work around an environment error.
