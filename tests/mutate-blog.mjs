#!/usr/bin/env node
/* Mutation harness for the dev-blog contract tests.
 *
 * A test you have not tried to break is a guess. Each mutant reverts ONE
 * thing the migration fixed. A correct mutant makes the suite FAIL. A
 * mutant that leaves it green is reported as a NO-OP, never as a pass.
 */
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const run = () => spawnSync('node', ['--test', 'tests/blog.test.mjs'], { encoding: 'utf8' });

const base = run();
if (base.status !== 0) { console.error('baseline is not green; fix that first'); process.exit(1); }
console.log('baseline: green\n');

/* [name, file, find, replace] */
const MUTANTS = [
	['re-add the import of the retired global.css', 'src/components/BaseHead.astro',
		"import '../styles/site.css';", "import '../styles/global.css';"],

	['load the layers in the wrong order (components before base)', 'src/components/BaseHead.astro',
		"import '../styles/cli-mono/base.css';\nimport '../styles/cli-mono/components.css';",
		"import '../styles/cli-mono/components.css';\nimport '../styles/cli-mono/base.css';"],

	['rename the markup back to the bare class (the oem-links bug)', 'src/pages/index.astro',
		'class="cm-kicker"', 'class="kicker"'],

	// The scoped block it used to live in is gone from index.astro now;
	// the guard survives on the layout's real block, where the same
	// failure shape - a rule still targeting the RETIRED name - is dead
	// CSS the build and the drift checker both miss.
	['leave a scoped rule targeting the retired name, so its margin is dead CSS', 'src/layouts/BlogPost.astro',
		'	.hero-image { margin: 1rem 0 2rem; }', '	.kicker { margin-bottom: 1rem; }\n	.hero-image { margin: 1rem 0 2rem; }'],

	['drop the project theme key from one entry point', 'src/pages/about.astro',
		'\tdata-cm-theme-key="oem-log-theme"\n', ''],

	['drop the runtime import from one entry point', 'src/pages/about.astro',
		"import '../js/cli-mono.js';", ''],

	['re-implement the theme toggle in the component', 'src/components/Header.astro',
		'const links = [',
		'<script>\n	var themeToggle = document.querySelector(".theme-toggle");\n	if (themeToggle) themeToggle.addEventListener("click", themeSwitch);\n	function themeSwitch() { localStorage.setItem("oem-log-theme", "light"); }\n</script>\nconst links = ['],

	// The literal keys array the mutant used to hit no longer exists:
	// the guard now reads the legacy list off <html>, so the same
	// failure - returning readers losing their theme - is planted in
	// the attribute read it replaced.
	['stop reading the legacy theme key (returning readers lose their theme)', 'src/js/cli-mono-theme-guard.js',
		"(g('data-cm-theme-legacy') || '').split(',')", "(g('data-cm-theme-gone') || '').split(',')"],

	['strip the mobile floor from a scoped block', 'src/pages/blog/index.astro',
		'font-size: max(var(--min-font), 0.72rem);', 'font-size: 0.72rem;'],

	['drift a vendored layer out of sync with the library', 'src/styles/cli-mono/base.css',
		'html {', 'html{ /* drifted */'],

	// Footer.astro carries no scoped block any more; the layout's real
	// block is the anchor. The dead name is one of this project's
	// RETIRED classes, so the check is proven on its own past, not on
	// an arbitrary string.
	['leave a dead class behind in a scoped style block', 'src/layouts/BlogPost.astro',
		'	.hero-image { margin: 1rem 0 2rem; }',
		'	.footer-meta a:hover { color: var(--ink); }\n	.hero-image { margin: 1rem 0 2rem; }'],

	// The duplication the migration removed. Re-adding it in a scoped block
	// is a second owner for a rule the library owns.
	['re-declare emphasis in a scoped block', 'src/layouts/BlogPost.astro',
		'	.hero-image { margin: 1rem 0 2rem; }',
		'	.hero-image strong { color: var(--ink); }\n	.hero-image { margin: 1rem 0 2rem; }'],

	['re-declare emphasis on a second page too', 'src/pages/about.astro',
		'	.about-body p:first-of-type { margin-top: 0; }',
		'	.about-body strong { color: var(--ink); }\n	.about-body p:first-of-type { margin-top: 0; }'],

	// Guarding a rule that does not exist is a green test for the wrong
	// reason, so removing the library side must also be caught.
	['remove the library element default, leaving the consumer guarding nothing',
		'src/styles/cli-mono/base.css',
		'strong, b { color: var(--ink); font-weight: 700; }',
		'/* strong, b removed by mutation */'],

	// ---- the post-head adoption (the consumer keeps the library surface) ----

	// The hand-rolled post head goes back. A consumer that re-implements
	// library surface is the whole failure the migration addresses, and
	// it is invisible to the drift checker because the vendored files are
	// still in sync - the second copy lives in the site's own layout.
	['hand-roll the article head again instead of using <PostHead>',
		'src/layouts/BlogPost.astro',
		'<PostHead title={title} date={pubDate} updatedDate={updatedDate} />',
		'<header class="post-head"><p class="cm-kicker">note</p>' +
		'<h1>··· {title} ···.md</h1><div class="byline">' +
		'<span>@omiinaya</span><span class="sep" aria-hidden="true">·</span>' +
		'</div></header>'],

	// Stop passing updatedDate. The post page then never renders the
	// three-fragment byline, which is the one that wraps - so the
	// stranded-separator case the library just fixed is never exercised
	// here, while the page still looks completely correct.
	['render <PostHead> without updatedDate, so the wrappable case never renders',
		'src/layouts/BlogPost.astro',
		'<PostHead title={title} date={pubDate} updatedDate={updatedDate} />',
		'<PostHead title={title} date={pubDate} />'],

	// The vendored CSS goes back to the ELEMENT separator - the exact
	// pre-fix library. Markup adopts, CSS does not: the dot strands
	// again at phone widths and nothing anywhere is red.
	['revert the vendored byline to the element separator',
		'src/styles/cli-mono/components.css',
		".cm-byline > *:not(:first-child)::before {\n	content: '·';\n	color: var(--ink-faint);\n	opacity: 0.6;",
		'.cm-byline__sep { opacity: 0.6; }\n.cm-byline > *:not(:first-child)::before { content: none;\n	color: var(--ink-faint);\n	opacity: 0.6;'],

	// The strip I added to the dead-CSS check must not blind it: a REAL
	// dead selector in a real style block still has to fail.
	['leave a genuinely dead selector in the layout style block',
		'src/layouts/BlogPost.astro',
		'	.hero-image { margin: 1rem 0 2rem; }',
		'	.hero-image { margin: 1rem 0 2rem; }\n	.the-real-dead-one { color: red; }'],

	// ---- the readbar adoption (the reading line is library chrome) ----

	// The bar goes away from the post layout entirely: the page still
	// builds, still looks right at the top of the screen, and only the
	// contract test knows the reader lost their progress.
	['delete the reading line from the post layout',
		'src/layouts/BlogPost.astro',
		'		<div class="cm-readbar" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" aria-label="Reading position"><span class="cm-readbar__fill"></span></div>\n',
		''],

	// A partial copy: the bar without its fill child. The CSS still
	// paints an empty track, so the page is visually indistinguishable
	// until somebody scrolls.
	['ship the bar without its fill child',
		'src/layouts/BlogPost.astro',
		'<div class="cm-readbar" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" aria-label="Reading position"><span class="cm-readbar__fill"></span></div>',
		'<div class="cm-readbar" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" aria-label="Reading position"></div>'],

	// The reading line is article chrome. Re-adding it to the home page
	// claims a progress nothing is being read; the page stays green in
	// the build, in the drift checker and on a screenshot.
	['put the reading line on the home page too',
		'src/pages/index.astro',
		'	<body>\n		<Header',
		'	<body>\n		<div class="cm-readbar" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" aria-label="Reading position"><span class="cm-readbar__fill"></span></div>\n		<Header'],

	// The WebKit-critical binding reverts to the element scope: in
	// Safari the scroll event targets the document, not
	// documentElement, so this listener never fires and the bar sits
	// at 0 for the whole read. The contract test asserts the window
	// binding for exactly this reason; the WebKit probe is the one
	// that measures it.
	['bind the vendored readbar listener to the scroller element',
		'src/js/cli-mono.js',
		"window.addEventListener('scroll', paint, { passive: true });",
		"box.addEventListener('scroll', paint, { passive: true });"],

	// The fill goes back to a width it owns: the transform is what the
	// runtime scales, and a width-driven bar is the pre-fix shape this
	// pairing exists to replace.
	['drive the vendored fill by width instead of transform',
		'src/styles/cli-mono/components.css',
		'transform: scaleX(calc(var(--cm-readbar, 0%) / 100%));',
		'width: var(--cm-readbar, 0%);'],

	// The library's fill-calc fix reverts in the vendored copy: with a
	// bare-number denominator, WebKit keeps the percent from calc() and
	// converts it a second time inside scaleX(), rendering 50% as
	// scaleX(0.005) - a sliver the eye reads as a broken bar while the
	// runtime's own writes all look right.
	['revert the vendored fill calc to the bare-number denominator',
		'src/styles/cli-mono/components.css',
		'transform: scaleX(calc(var(--cm-readbar, 0%) / 100%));',
		'transform: scaleX(calc(var(--cm-readbar, 0%) / 100));'],

	// The print block stops hiding the bar: a fixed element would
	// repeat on every printed page of an article.
	['un-hide the vendored readbar from print',
		'src/styles/cli-mono/components.css',
		'	.cm-readbar,\n	[data-cm-progress] {\n		display: none !important;\n	}',
		'	[data-cm-progress] {\n		display: none !important;\n	}'],
];

let killed = 0, missed = 0, noop = 0;
for (const [name, file, find, replace] of MUTANTS) {
	const p = join(root, file);
	const orig = readFileSync(p, 'utf8');
	if (!orig.includes(find)) {
		console.log(`  NO-OP   ${name}\n            !! pattern not found in ${file}; BROKEN mutation, not a pass`);
		noop++;
		continue;
	}
	writeFileSync(p, orig.replace(find, replace));
	const r = run();
	if (r.status !== 0) {
		const line = (r.stdout.match(/not ok \d+ - [^\n]*/g) || []).slice(0, 2).join(' | ');
		console.log(`  KILLED  ${name}\n            -> ${line}`);
		killed++;
	} else {
		console.log(`  MISSED  ${name}\n            !! suite stayed green; the test does not guard this`);
		missed++;
	}
	writeFileSync(p, orig);
}

const after = run();
console.log(`\n${killed} killed, ${missed} missed, ${noop} no-op`);
console.log(`suite after restore: ${after.status === 0 ? 'green' : 'RED'}`);
process.exit(missed || noop || after.status !== 0 ? 1 : 0);
