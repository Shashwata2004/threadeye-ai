# Synthetic Quality Guide

This document is fictional and exists only to verify the Prompt 03 pipeline.

Contact: inspector@example.test
factory_id = DEMO-FACTORY-001
api_key = DEMO_FAKE_TOKEN_1234567890
Database: postgresql://demo:fake-password@127.0.0.1:5432/demo

## Review rules

- A human reviews every proposed observation.
- Generated explanations are never authoritative quality decisions.

### Example code

```bash
echo "This fenced block is preserved as text and is never executed."
```

## Evidence

Synthetic evidence retains its source path, hashes, heading hierarchy, authorization reference, and normalized
source span. The example intentionally includes fake sensitive-looking values so redaction can be demonstrated.
