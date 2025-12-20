// Initialize Mermaid with Iconify icon packs for architecture diagrams
// This enables icons like logos:prometheus, mdi:cog, etc.

// Wait for mermaid to be available (loaded via extra_javascript in mkdocs.yml)
document.addEventListener('DOMContentLoaded', async function() {
  if (typeof mermaid !== 'undefined') {
    // Register icon packs for architecture-beta diagrams
    mermaid.registerIconPacks([
      {
        name: 'logos',
        loader: () =>
          fetch('https://unpkg.com/@iconify-json/logos@1/icons.json').then((res) => res.json()),
      },
      {
        name: 'mdi',
        loader: () =>
          fetch('https://unpkg.com/@iconify-json/mdi@1/icons.json').then((res) => res.json()),
      },
    ]);

    // Re-initialize to pick up icon packs
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
    });

    // Run mermaid on any diagrams
    await mermaid.run();
  }
});
