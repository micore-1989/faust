---
name: echo
description: Echo a string back. Use to verify the agent loop is wired up.
parameters_schema:
  type: object
  properties:
    text:
      type: string
      description: Text to echo back
  required:
    - text
sensitivity: passive
allowed_tools:
  - echo
---

# Echo

Simple echo tool for smoke-testing the agent loop and skill loader. Returns
whatever text is passed in. No side effects.
