# TGS GitHub Pages deployment

The source app stays in `tgs2026/`. The Actions workflow publishes its contents at the **website root**, without overwriting the repository's pre-existing index.html or other pages. The old nested `/tgs2026/` site path redirects to the website root in the generated artifact.

## Account settings (repository administrator)

1. Settings > General > Repository name: rename `test.github.io` to `tgs2026`.
2. Settings > Pages > Build and deployment > Source: select **GitHub Actions**.
3. Actions > **Deploy TGS map to GitHub Pages** > Run workflow > master.

This does not require supplying a personal access token to the workflow. The workflow cannot rename the repository or enable Pages administration itself.

Use the actual URL shown by the successful deployment. The expected default project URL after renaming is `https://aatr0x13.github.io/tgs2026/`; this is not a claim that the site is already live.

## Image-integrity repair

The originally committed `tgs2026/map.webp` has a RIFF header declaring 705502 bytes, but only 14028 bytes reached the repository. A file existing in Git is not evidence that it can decode.

Before publishing, the build validates the JavaScript, minimum index counts, WebP container length, pixel decoding and dimensions. An invalid image is regenerated from the original official PDF. The PDF must match SHA-256 `231244de5827b79da0af83f079a6f42c6b531695767bb5366c9a7d580729ccef`. The build never silently substitutes a different map version.

If the official PDF download is unavailable, upload the original attached PDF to `source/2026_TGS_MAP_0914_EN.pdf` and rerun. Alternatively replace `tgs2026/map.webp` with the validated 3827 x 2232 WebP provided with the repair handoff. Existing source coordinates are not changed. Generated output is in the `github-pages` artifact; a successful deployment is separate from build/upload success.

Official references:
- https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository
- https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site
