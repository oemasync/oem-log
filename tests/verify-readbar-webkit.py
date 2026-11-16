# WebKit measurement of the reading-progress line on oem/log's post pages.
#
# The source-level contract proves the bar is WRITTEN and that the vendored
# CSS, token and runtime carry the complete pair. This probe proves the
# bar BEHAVES in the engine readers actually use: the geometry the CSS
# claims (fixed, full-width, above the header, pointer-transparent), the
# pairing (the fill, the custom property and aria-valuenow all read one
# value), and the behaviour only the runtime provides - the fill
# following the document scroller as the article scrolls.
#
# A green build check and a screenshot at the top of the page both show
# an empty track: nothing there can see a bar that never moves, and the
# WebKit-specific failure shape (the scroll listener bound to the
# scroller element, which never fires in this engine) is invisible to
# both. That shape is exactly what tests/negctl-readbar-webkit.py
# requires this probe to catch.
#
# Run against the LAN preview (BLOG_URL, default http://192.168.1.68:4322).
from playwright.sync_api import sync_playwright
import os, re, sys

# Probes self-rescue a dead PLAYWRIGHT_BROWSERS_PATH: the host export may
# point at a cache that holds no webkit build, and playwright then refuses
# to launch. Delete the var only when the named cache lacks a webkit build
# - an unconditional delete would discard a restored cache.
_pw = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if _pw and (not os.path.isdir(_pw) or not any(
        d.startswith("webkit-") for d in os.listdir(_pw)
        if os.path.isdir(os.path.join(_pw, d)))):
    del os.environ["PLAYWRIGHT_BROWSERS_PATH"]

BASE = os.environ.get("BLOG_URL", "http://192.168.1.68:4322")
POSTS = [
	"/blog/a-hundred-tor-exits-kept-alive-and-honest/",
	"/blog/building-a-self-healing-watchdog/",
	"/blog/getting-tracking-data-from-fedex-consistently/",
]
NO_BAR_PAGES = ["/", "/blog/", "/about/"]

GEOM = """() => {
	const bar = document.querySelector('.cm-readbar');
	if (!bar) return { error: 'no .cm-readbar on page' };
	const fill = bar.querySelector('.cm-readbar__fill');
	const hdr = document.querySelector('.cm-header');
	const cs = getComputedStyle(bar);
	const root = getComputedStyle(document.documentElement);
	const r = bar.getBoundingClientRect();
	// The token arrives as a unit (".25rem"); getPropertyValue never
	// resolves it, so the height is compared against the token measured
	// on a throwaway box, not against the raw string.
	const probe = document.createElement("i");
	probe.style.height = "var(--space-1)";
	probe.style.display = "block";
	document.body.appendChild(probe);
	const space1 = getComputedStyle(probe).height;
	probe.remove();
	return {
		pos: cs.position, top: cs.top, left: cs.left,
		width: cs.width, height: cs.height,
		space1: space1,
		z: cs.zIndex, hdrZ: hdr ? getComputedStyle(hdr).zIndex : null,
		pe: cs.pointerEvents,
		fillTransform: fill ? getComputedStyle(fill).transform : null,
		origin: fill ? getComputedStyle(fill).transformOrigin : null,
		val: bar.style.getPropertyValue('--cm-readbar'),
		aria: bar.getAttribute('aria-valuenow'),
		min: bar.getAttribute('aria-valuemin'),
		max: bar.getAttribute('aria-valuemax'),
		role: bar.getAttribute('role'),
		rectTop: r.top, rectW: r.width,
		winW: window.innerWidth,
		scrollMax: (document.scrollingElement.scrollHeight -
			document.scrollingElement.clientHeight),
	};
}"""

def check(name, cond, detail=""):
	global failed
	if cond:
		print(f"  ok    {name}")
	else:
		failed += 1
		print(f"  FAIL  {name}  {detail}")

def wait_runtime(pg):
	# The runtime marks itself; a millisecond wait is a guess.
	pg.wait_for_function(
		"() => document.documentElement.classList.contains('cm-js') || !!window.cliMono",
		timeout=15000)
	pg.wait_for_timeout(120)

def track(pg, frac, label, tol):
	"""Scroll to frac of the scroller, settle, read the three ways."""
	max_ = pg.evaluate("() => document.scrollingElement.scrollHeight - "
		"document.scrollingElement.clientHeight")
	target = max_ * frac
	pg.evaluate("y => window.scrollTo(0, y)", target)
	pg.wait_for_function("y => Math.abs(window.scrollY - y) < 2",
		arg=target, timeout=5000)
	pg.wait_for_timeout(320)  # let the fill's transform transition settle
	v = pg.evaluate("""() => {
		const bar = document.querySelector('.cm-readbar');
		const fill = bar.querySelector('.cm-readbar__fill');
		const m = getComputedStyle(fill).transform.match(
			/matrix\\(([-\\d.]+)/);
		return {
			val: bar.style.getPropertyValue('--cm-readbar'),
			aria: parseInt(bar.getAttribute('aria-valuenow'), 10),
			sx: m ? parseFloat(m[1]) : null,
			y: window.scrollY,
		};
	}""")
	expect = frac * 100
	# The pairing the component promises: the custom property, the aria
	# attribute and the fill's scale all read the SAME number.
	ok = (abs(v["aria"] - expect) <= tol
		and abs(float(v["val"].rstrip("%")) - expect) <= tol
		and abs(v["sx"] - frac) <= tol / 100 + 0.005)
	check(f"{label}: one value in all three readings (y={v['y']:.0f})",
		ok, f"--cm-readbar={v['val']} aria={v['aria']} scaleX={v['sx']:.3f} "
			f"expected~{expect:.0f}")
	return v

failed = 0

with sync_playwright() as p:
	b = p.webkit.launch()

	# ---- geometry and tracking, at the widths readers use ----
	for w, h in ((402, 874), (390, 844), (1280, 900)):
		pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
		# pick the LONGEST post at this width: a fixture that fits the
		# cap never scrolls, so the tracking path is never exercised.
		best = None
		for post in POSTS:
			pg.goto(BASE + post, wait_until="networkidle")
			wait_runtime(pg)
			sm = pg.evaluate(
				"() => document.scrollingElement.scrollHeight - "
				"document.scrollingElement.clientHeight")
			if best is None or sm > best[1]:
				best = (post, sm)
		post, max_ = best
		print(f"\n@ {w}x{h} - {post} (scroller: {max_:.0f}px)")
		if max_ < 200:
			check("the fixture scrolls", False,
				f"scrollable area is only {max_:.0f}px; "
				"a bar on a page that cannot scroll proves nothing")
			pg.close()
			continue
		g = pg.evaluate(GEOM)
		check("the bar exists", "error" not in g, str(g))
		if "error" in g:
			pg.close()
			continue
		check("fixed to the viewport", g["pos"] == "fixed", g["pos"])
		check("hugs the top edge", g["top"] == "0px", g["top"])
		check("hugs the start edge", g["left"] == "0px", g["left"])
		check("spans the viewport", g["width"] == f"{g['winW']}px",
			f"width={g['width']} win={g['winW']}")
		check("hugs --space-1", g["height"] == g["space1"],
			f"height={g['height']} --space-1={g['space1']}")
		check("sits above the header",
			g["z"] == "120" and g["hdrZ"] == "100",
			f"bar z={g['z']} header z={g['hdrZ']}")
		check("is pointer-transparent", g["pe"] == "none", g["pe"])
		check("starts empty (no runtime lie)",
			g["val"] in ("0%", "") and g["aria"] == "0"
			and g["rectTop"] == 0,
			f"val={g['val']} aria={g['aria']} top={g['rectTop']}")
		check("the fill is transform-driven",
			g["fillTransform"] is not None
			and g["fillTransform"].startswith("matrix(0,"),
			g["fillTransform"])
		# pointer transparency is behaviour, not a style: a tap on the
		# line reaches the header chrome beneath it, never the bar.
		hit = pg.evaluate("""w => {
			const el = document.elementFromPoint(w / 2, 2);
			const bar = document.querySelector('.cm-readbar');
			return { el: el ? el.className || el.tagName : null,
				isBar: el === bar, inBar: el ? bar.contains(el) : false };
		}""", w)
		check("a tap on the line reaches the page, not the bar",
			hit["el"] is not None and not hit["isBar"] and not hit["inBar"],
			str(hit))
		track(pg, 0.5, "scroll to half", 2)
		track(pg, 1.0, "scroll to the end", 1)
		track(pg, 0.0, "back to the top", 0)
		pg.close()

	# ---- reduced motion: the fill's transition must be silenced ----
	pg = b.new_page(viewport={"width": 390, "height": 844})
	pg.emulate_media(reduced_motion="reduce")
	pg.goto(BASE + POSTS[0], wait_until="networkidle")
	wait_runtime(pg)
	tp = pg.evaluate(
		"() => getComputedStyle("
		"document.querySelector('.cm-readbar__fill')).transitionProperty")
	print("\n@ reduced motion")
	check("the fill has no transition under reduced motion",
		tp == "none", f"transition-property={tp}")
	pg.close()

	# ---- print: a fixed element repeats on every page, so it is hidden ----
	pg = b.new_page(viewport={"width": 794, "height": 1123})
	pg.emulate_media(media="print")
	pg.goto(BASE + POSTS[0], wait_until="networkidle")
	d = pg.evaluate(
		"() => getComputedStyle("
		"document.querySelector('.cm-readbar')).display")
	print("\n@ print (A4 page box)")
	check("the bar is hidden in print", d == "none", f"display={d}")
	pg.close()

	# ---- the line is article chrome: no other page carries it ----
	pg = b.new_page(viewport={"width": 390, "height": 844})
	print("\n@ non-article pages")
	for path in NO_BAR_PAGES:
		pg.goto(BASE + path, wait_until="networkidle")
		n = pg.evaluate(
			"() => document.querySelectorAll('.cm-readbar').length")
		check(f"{path} carries no reading line", n == 0, f"found {n}")
	pg.close()

	b.close()

print(f"\n{failed} failure(s)")
sys.exit(1 if failed else 0)
