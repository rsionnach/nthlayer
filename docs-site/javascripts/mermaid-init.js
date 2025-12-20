// Initialize Mermaid with Iconify icon packs for architecture diagrams

window.addEventListener('load', async function() {
  if (typeof mermaid === 'undefined') {
    console.error('Mermaid not loaded');
    return;
  }

  try {
    // 1. Register icon packs with loader functions (per Mermaid docs)
    mermaid.registerIconPacks([
      {
        name: 'logos',
        loader: () => fetch('https://unpkg.com/@iconify-json/logos@1/icons.json').then(r => r.json()),
      },
      {
        name: 'mdi',
        loader: () => fetch('https://unpkg.com/@iconify-json/mdi@1/icons.json').then(r => r.json()),
      },
    ]);
    console.log('Icon packs registered');

    // 2. Fix HTML-escaped content and prepare divs for mermaid
    const mermaidBlocks = document.querySelectorAll('pre.mermaid');
    console.log('Found', mermaidBlocks.length, 'mermaid blocks');

    mermaidBlocks.forEach((pre, index) => {
      const code = pre.querySelector('code');
      if (code) {
        // textContent automatically decodes HTML entities
        const content = code.textContent;
        console.log('Block', index, 'first line:', content.split('\n')[0]);

        // Create a clean div for mermaid
        const div = document.createElement('div');
        div.className = 'mermaid';
        div.textContent = content;

        // Replace pre with div
        pre.parentNode.replaceChild(div, pre);
      }
    });

    // 3. Initialize and run mermaid
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
    });

    console.log('Running mermaid.run()...');
    await mermaid.run({
      querySelector: '.mermaid',
    });
    console.log('Mermaid rendering complete');

  } catch (error) {
    console.error('Mermaid init error:', error);
  }
});
