---
name: add
description: Add two integers and return the sum.
parameters_schema:
  type: object
  properties:
    a:
      type: integer
      description: First operand
    b:
      type: integer
      description: Second operand
  required:
    - a
    - b
typical_duration_s: 1
sensitivity: passive
allowed_tools:
  - add
---

# Add

Arithmetic addition tool for dev testing. Takes two integers, returns their sum.
