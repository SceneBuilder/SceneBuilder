## Cryptomatte Highlight Implementation Notes

- Highlights now use Cryptomatte V2 (object layer) instead of Object Index. Renderer preference for highlight paths is EEVEE (falls back to whatever `_configure_render_settings` can select). The compositor chain remains Blur → Subtract → Multiply (tint) → Glare → Add, but the mask source is Cryptomatte’s Matte output.
- Crypto passes are enabled only when highlight targets are provided: `use_pass_crypto_object = True`, depth clamped to at least 6, with `crypto_accurate` enabled to reduce hash collisions.
- Targets are derived from mesh descendant names of the requested logical objects. The Cryptomatte V2 node reads the active view layer automatically; we populate its `matte_id` field with the comma-separated mesh names instead of wiring individual CryptoObject sockets.
- Lighting foundation no longer forces Cycles, so highlight renders can stay on EEVEE while still reusing the world setup.

Open questions / follow-ups:
- Verify the exact Blender API for populating matte IDs across versions (the code tries `add_matte`, then the Matte ID socket). If a targeted Blender build exposes a different API surface, consider adding an adapter util to normalize this.
- For duplicated/instanced assets, ensure mesh names remain stable across frames so Cryptomatte IDs resolve consistently. If instability appears, inject a deterministic `crypto_asset` custom property or name suffix before rendering.
