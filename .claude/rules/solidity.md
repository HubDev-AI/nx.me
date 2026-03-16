---
alwaysApply: false
globs: "*.sol"
---
Solidity conventions — loaded when working with .sol files.

# Solidity Standards

## NatSpec Documentation

NatSpec is **required**, not optional — it is part of the Solidity ABI, consumed by Etherscan, block explorers, wallets, and audit tools (`solc --userdoc`, `solc --devdoc`). Always include NatSpec when writing or modifying Solidity code.

- **Every public/external function** must have `@notice`, `@param`, and `@return`
- **Every contract/interface** must have `@title` and `@author`
- **Every event and custom error** must have `@notice` and `@param`
- **Public state variables** must have `@notice`
- Use `@inheritdoc` when overriding to inherit parent documentation

## Interface-First Design

Define interfaces before implementations. Contracts inherit their interface and use `@inheritdoc`.

- **Every contract** should have a corresponding `I{Name}.sol` interface file
- **Define custom errors and events in the interface** — consumers need them without importing the implementation
- **Contracts inherit their interface** — `contract Vault is IVault`
- **NatSpec in both interface and implementation** — developers read implementations directly; do not force them to jump to the interface to understand a function. Use `@inheritdoc` only when the implementation adds nothing beyond what the interface says
