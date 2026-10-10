# Security

For vulnerabilities in URL handling, local file writing or model-tool boundaries, contact maintainers privately before publishing details in an issue. Until maintainers designate a public contact, do not include real API keys, tokens or customer datasets in bug reports.

This prototype is intended for trusted single-user execution. Do not expose its CLI as an unauthenticated multi-user internet service. Web content is untrusted and potentially malicious; a model may follow instructions found on webpages. The network URL pre-checks are best-effort and **do not prevent DNS rebinding on their own**. Use a restricted egress environment for sensitive deployments.
