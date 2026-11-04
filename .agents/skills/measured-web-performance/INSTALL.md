# Personal Codex installation

This folder is a portable skill. The xyz_transcript_download reference is optional and applies only to that repository.

## Install from GitHub

In Codex on the machine you use for your projects, invoke the built-in installer:

> $skill-installer Install https://github.com/aaronsxzhao/xyz_transcript_download/tree/main/.agents/skills/measured-web-performance as a personal skill available across repositories.

## Install from the ZIP

Extract the package and put its `measured-web-performance` folder under `~/.agents/skills/` on that machine. Preserve the references and assets subfolders. If that name already exists, inspect it before replacing it. Do not overwrite customized skills blindly.

Codex discovers user skills across projects. If it does not appear, restart Codex. Invoke `$measured-web-performance` or select it through `/skills`. A repository-local copy with the same name may also appear; choose the intended copy rather than assuming they merge.

User-level installation is local to the machine/user home. It is not an account-wide sync mechanism for other computers or independent cloud workers. Install separately in each environment, or distribute through a supported plugin mechanism. Creating this package does not install it on your desktop.

Documentation: https://developers.openai.com/codex/skills/
