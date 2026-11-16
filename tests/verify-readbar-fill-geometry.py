#!/usr/bin/env python3
"""Prove the readbar fill is NOT 1/100th of the bar in WebKit.

The shipped denominator (`/ 100`) rendered 50% as scaleX(0.005) -
a sliver 1/100th of the read - while the runtime's own writes all
looked correct. This probe measures the fill's painted width against
the bar's own width at three authored positions, which is the one
reading the runtime's writes cannot fake.

A bar at 50% must paint roughly half its width. The shipped bug
would paint 0.5%.
"""
import os
import sys
from playwright.sync_api import sync_playwright

# Probes self-rescue a dead PLAYWRIGHT_BROWSERS_PATH: the host export may
# point at a cache that holds no webkit build, and playwright then refuses
# to launch. Delete the var only when the named cache lacks a webkit build
# - an unconditional delete would discard a restored cache.
_pw = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if _pw and (not os.path.isdir(_pw) or not any(
        d.startswith("webkit-") for d in os.listdir(_pw)
        if os.path.isdir(os.path.join(_pw, d)))):
    del os.environ["PLAYWRIGHT_BROWSERS_PATH"]

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.1.68:4322"
POST = "/blog/getting-tracking-data-from-fedex-consistently/"
# The bar is article chrome: only post layouts carry it, so every page
# that is NOT a post must measure empty. A static specimen would need a
# frozen --cm-readbar value, which this project's pages do not have -
# the runtime drives the only bar on the site.
NON_POSTS = ["/", "/blog/", "/about/"]

def measure(pg, path):
    # `wait_until='load'` never resolves here, and the first wait_for_function
    # after a 'commit' navigation lies (className already reads cm-js,
    # cliMono is defined, and the call still times out at 10.9s). Poll
    # evaluate instead, and never a timer - the same doctrine as the
    # showcase harness.
    pg.goto(BASE + path, wait_until="commit")
    import time
    t0 = time.time()
    while time.time() - t0 < 15:
        if pg.evaluate(
                "() => document.documentElement.classList.contains('cm-js') "
                "|| !!window.cliMono"):
            break
        pg.wait_for_timeout(200)
    else:
        raise RuntimeError("runtime mark never appeared on " + path)
    pg.wait_for_timeout(120)
    return pg.evaluate("""() => {
        const bars = [...document.querySelectorAll('.cm-readbar')];
        return bars.map(b => {
            const r = b.getBoundingClientRect();
            const f = b.querySelector('.cm-readbar__fill');
            const fr = f.getBoundingClientRect();
            const cs = getComputedStyle(f);
            return {
                w: Math.round(r.width), h: Math.round(r.height),
                fw: Math.round(fr.width),
                transform: cs.transform,
                readbar: b.style.getPropertyValue('--cm-readbar'),
                aria: b.getAttribute('aria-valuenow'),
            };
        });
    }""")

def main():
    with sync_playwright() as p:
        b = p.webkit.launch()
        pg = b.new_page(viewport={"width": 402, "height": 874},
                        device_scale_factor=2)
        print("== blog post (runtime-driven, starts at 0) ==")
        posts = measure(pg, POST)
        assert len(posts) == 1, f"post carries {len(posts)} bars, expected 1"
        m = posts[0]
        assert m["w"] > 0 and m["h"] > 0, "post bar is not rendered"
        assert m["fw"] == 0, f"post bar starts at {m['fw']}px, not 0"
        assert m["readbar"] == "0%", f"post bar reads {m['readbar']!r}, not 0%"
        assert m["aria"] == "0", f"post bar aria is {m['aria']!r}, not 0"
        assert "matrix(0" in m["transform"], \
            f"fill is not transform-driven: {m['transform']!r}"
        print(f"  bar {m['w']}x{m['h']} fill {m['fw']}px "
              f"({m['fw']/max(m['w'],1)*100:.1f}%) "
              f"transform={m['transform']!r} "
              f"--cm-readbar={m['readbar']!r} aria={m['aria']}")
        print("== non-article pages (must carry no reading line) ==")
        for page in NON_POSTS:
            bars = measure(pg, page)
            assert len(bars) == 0, f"{page} carries {len(bars)} bars"
            print(f"  {page}: 0 bars (no reading line, as authored)")
        pg.close(); b.close()

if __name__ == "__main__":
    main()