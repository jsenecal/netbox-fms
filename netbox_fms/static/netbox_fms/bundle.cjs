const esbuild = require('esbuild');
const path = require('path');

const isWatch = process.argv.includes('--watch');

const shared = {
  bundle: true,
  minify: !isWatch,
  sourcemap: 'linked',
  target: 'es2016',
  external: ['d3'],
  format: 'iife',
  logLevel: 'info',
};

const entries = [
  {
    entryPoints: [path.join(__dirname, 'src', 'splice-editor.ts')],
    globalName: 'SpliceEditor',
    outfile: path.join(__dirname, 'dist', 'splice-editor.min.js'),
  },
  {
    entryPoints: [path.join(__dirname, 'src', 'trace-view.ts')],
    globalName: 'TraceView',
    outfile: path.join(__dirname, 'dist', 'trace-view.min.js'),
  },
  {
    entryPoints: [path.join(__dirname, 'src', 'fms-htmx.ts')],
    globalName: 'FmsHtmx',
    outfile: path.join(__dirname, 'dist', 'fms-htmx.min.js'),
  },
];

async function main() {
  if (isWatch) {
    for (const entry of entries) {
      const ctx = await esbuild.context({ ...shared, ...entry });
      await ctx.watch();
    }
    console.log('Watching for changes...');
  } else {
    await Promise.all(entries.map((entry) => esbuild.build({ ...shared, ...entry })));
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
