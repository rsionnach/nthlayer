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

    // Initialize mermaid
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
    });

    // Fix HTML-escaped content in mermaid blocks before rendering
    // mkdocs escapes > to &gt; which breaks arrows like -->
    document.querySelectorAll('pre.mermaid code, .mermaid code').forEach((el) => {
      // Decode HTML entities
      const decoded = el.textContent
        .replace(/&gt;/g, '>')
        .replace(/&lt;/g, '<')
        .replace(/&amp;/g, '&');

      // Create a new div with the decoded content for mermaid to process
      const div = document.createElement('div');
      div.className = 'mermaid';
      div.textContent = decoded;

      // Replace the pre>code structure with the div
      const pre = el.closest('pre.mermaid') || el.closest('.mermaid');
      if (pre && pre.parentNode) {
        pre.parentNode.replaceChild(div, pre);
      }
    });

    // Run mermaid on all .mermaid elements
    await mermaid.run();
  }
});
