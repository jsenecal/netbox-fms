const esbuild = require('esbuild');
const path = require('path');

const isWatch = process.argv.includes('--watch');

const buildOptions = {
  entryPoints: [path.join(__dirname, 'src', 'splice-editor.ts')],
  bundle: true,
  minify: !isWatch,
  sourcemap: 'linked',
  target: 'es2016',
  outdir: path.join(__dirname, 'dist'),
  outExtension: { '.js': '.min.js' },
  external: ['d3'],
  format: 'iife',
  globalName: 'SpliceEditor',
  logLevel: 'info',
};

async function main() {
  if (isWatch) {
    const ctx = await esbuild.context(buildOptions);
    await ctx.watch();
    console.log('Watching for changes...');
  } else {
    await esbuild.build(buildOptions);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
