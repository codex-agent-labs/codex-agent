// Bootstrap without toolkit imports: a fresh checkout has no node_modules yet.
if (process.env.INPUT_MODE === 'execute') await import('./execute.mjs');
else await (await import('./cache.mjs')).main();
