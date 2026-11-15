# Cloudflare Origin CA public trust roots

`cloudflare-origin-ca.pem` contains only the public RSA and ECC Origin CA
certificates published by Cloudflare. It contains no server certificate or
private key. The installer reads this local bundle, so a blocked documentation
download cannot prevent installation.

Retrieved over verified HTTPS on 2026-11-15 from:

- https://developers.cloudflare.com/ssl/static/origin_ca_rsa_root.pem
- https://developers.cloudflare.com/ssl/static/origin_ca_ecc_root.pem

Official instructions:
https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/

Certificate SHA-256 fingerprints (DER):

- RSA: `d3c7e85c91707fc0a12abc5d88266747aa4fa8e7b162f633ffb3c9d989947620`
- ECC: `aa63697a22764b67b2134ce14cb5690ea336940b93986113f49545917832d80d`

Both roots expire on 2029-08-15 at 17:00:00 UTC. Refresh from the official
source before expiration or if Cloudflare changes its Origin CA roots.
The optional `--origin-ca` argument selects an explicitly trusted local PEM
instead. The system CA store is never modified.
