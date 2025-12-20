// Initialize Mermaid with Iconify icon packs for architecture diagrams
// Sequence: Load icons -> Register -> Fix HTML escaping -> Render

window.addEventListener('load', async function() {
  if (typeof mermaid === 'undefined') {
    console.error('Mermaid not loaded');
    return;
  }

  try {
    // 1. Load icon packs in parallel
    console.log('Loading icon packs...');
    const [logosIcons, mdiIcons] = await Promise.all([
      fetch('https://unpkg.com/@iconify-json/logos@1/icons.json').then(r => r.json()),
      fetch('https://unpkg.com/@iconify-json/mdi@1/icons.json').then(r => r.json()),
    ]);
    console.log('Icon packs loaded');

    // 2. Register icon packs with mermaid
    mermaid.registerIconPacks([
      { name: 'logos', icons: logosIcons },
      { name: 'mdi', icons: mdiIcons },
    ]);
    console.log('Icon packs registered');

    // 3. Initialize mermaid (don't auto-start, we'll run manually)
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
    });

    // 4. Fix HTML-escaped content and prepare divs for mermaid
    const mermaidBlocks = document.querySelectorAll('pre.mermaid');
    console.log('Found', mermaidBlocks.length, 'mermaid blocks');

    mermaidBlocks.forEach((pre, index) => {
      const code = pre.querySelector('code');
      if (code) {
        // textContent automatically decodes HTML entities
        const content = code.textContent;
        console.log('Block', index, 'content preview:', content.substring(0, 50));

        // Create a clean div for mermaid
        const div = document.createElement('div');
        div.className = 'mermaid';
        div.textContent = content;

        // Replace pre with div
        pre.parentNode.replaceChild(div, pre);
      }
    });

    // 5. Run mermaid on all prepared divs
    console.log('Running mermaid.run()...');
    await mermaid.run({
      querySelector: '.mermaid',
    });
    console.log('Mermaid rendering complete');

  } catch (error) {
    console.error('Mermaid init error:', error);
  }
});
