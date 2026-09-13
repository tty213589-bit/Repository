(() => {
  'use strict';

  const MAX_IMAGES = 14;
  const BAD_LINE = /(captcha|verify|login|访问频繁|安全验证|机器人|请登录|滑块验证)/i;
  const NAV_NOISE = /(淘宝网|天猫首页|购物车|我的淘宝|联系客服|网站导航|登录|注册|download app|open app)/i;

  function cleanText(v, max = 240) {
    return String(v || '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\[[^\]]*\]\([^)]*\)/g, ' ')
      .replace(/^[#>*+\-\s]+/, '')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, max);
  }

  function uniq(arr) {
    return [...new Set(arr.filter(Boolean))];
  }

  function itemIdFrom(url) {
    try {
      const u = new URL(url);
      const id = u.searchParams.get('id') || u.searchParams.get('itemId') || u.searchParams.get('item_id');
      if (id && /^\d{6,}$/.test(id)) return id;
      const m = u.pathname.match(/(?:item|i)[\/_-]?(\d{6,})/i) || u.href.match(/[?&](?:id|itemId|item_id)=(\d{6,})/i);
      return m ? m[1] : '';
    } catch { return ''; }
  }

  function candidateUrls(url) {
    const out = [url];
    const id = itemIdFrom(url);
    if (id) {
      out.push(`https://item.taobao.com/item.htm?id=${id}`);
      out.push(`https://h5.m.taobao.com/awp/core/detail.htm?id=${id}`);
      out.push(`https://detail.tmall.com/item.htm?id=${id}`);
    }
    return uniq(out);
  }

  function normalizeImage(u) {
    return String(u || '')
      .replace(/&amp;/g, '&')
      .replace(/^\/\//, 'https://')
      .replace(/[)>\]"']+$/g, '')
      .trim();
  }

  function goodImage(u) {
    if (!/^https?:\/\//i.test(u)) return false;
    if (/(logo|icon|sprite|avatar|qrcode|qr-code|favicon|placeholder|blank\.gif)/i.test(u)) return false;
    return /(alicdn|taobaocdn|tbcdn|imgextra|gw\.alicdn|img\.alicdn|\.jpg|\.jpeg|\.png|\.webp)/i.test(u);
  }

  function extractImages(text) {
    const found = [];
    const push = u => {
      u = normalizeImage(u);
      if (goodImage(u) && !found.includes(u)) found.push(u);
    };
    for (const m of String(text).matchAll(/!\[[^\]]*\]\((https?:\/\/[^)\s]+)[^)]*\)/gi)) push(m[1]);
    for (const m of String(text).matchAll(/(?:src|data-src)=["'](https?:\/\/[^"']+)["']/gi)) push(m[1]);
    for (const m of String(text).matchAll(/https?:\/\/[^\s)"'<>]+?(?:\.jpe?g|\.png|\.webp)(?:\?[^\s)"'<>]*)?/gi)) push(m[0]);
    return found.slice(0, MAX_IMAGES);
  }

  function priceFromLines(lines) {
    const candidates = [];
    const scoreLine = l => {
      let score = 0;
      if (/(到手价|券后价|促销价|活动价|现价|售价|price|sale price)/i.test(l)) score += 8;
      if (/(价格|price|¥|￥|元)/i.test(l)) score += 3;
      if (/(起|起价|from)/i.test(l)) score += 1;
      if (/(包邮门槛|满\s*\d+|优惠券|红包|省\s*¥|运费|shipping|free shipping)/i.test(l)) score -= 5;
      return score;
    };
    lines.forEach((line, idx) => {
      const patterns = [
        /(?:¥|￥|CNY|RMB)\s*([0-9]{1,7}(?:\.[0-9]{1,2})?)/gi,
        /(?:到手价|券后价|促销价|活动价|现价|售价|价格|price)\s*[:：]?\s*([0-9]{1,7}(?:\.[0-9]{1,2})?)/gi,
        /([0-9]{1,7}(?:\.[0-9]{1,2})?)\s*元\b/g,
      ];
      for (const re of patterns) {
        for (const m of line.matchAll(re)) {
          const v = Number(m[1]);
          if (v > 0.01 && v < 1000000) candidates.push({ v, score: scoreLine(line), idx, line });
        }
      }
    });
    if (!candidates.length) return 0;
    candidates.sort((a,b) => b.score - a.score || a.idx - b.idx || a.v - b.v);
    return candidates[0].v;
  }

  function firstMatching(lines, re, max = 120) {
    const l = lines.find(x => re.test(x));
    if (!l) return '';
    const after = l.split(/[:：]/).slice(1).join(':').trim();
    return cleanText(after || l, max);
  }

  function extractTitle(lines) {
    const explicit = lines.find(x => /^title\s*:/i.test(x));
    if (explicit) {
      const t = cleanText(explicit.replace(/^title\s*:/i, ''), 180);
      if (t && !NAV_NOISE.test(t)) return t;
    }
    const heads = lines
      .filter(x => /^#{1,3}\s+/.test(x))
      .map(x => cleanText(x.replace(/^#{1,3}\s+/, ''), 180))
      .filter(x => x.length >= 8 && !NAV_NOISE.test(x));
    if (heads[0]) return heads[0];
    const candidates = lines
      .map(x => cleanText(x, 180))
      .filter(x => x.length >= 12 && x.length <= 180 && !NAV_NOISE.test(x) && !/^https?:/i.test(x) && !/[¥￥]\s*\d/.test(x));
    return candidates[0] || '';
  }

  function extractVariants(lines) {
    const out = [];
    const add = s => {
      s = cleanText(s, 80).replace(/^(颜色分类|颜色|款式|型号|规格|尺寸|选择)\s*[:：]?\s*/i, '');
      if (s && s.length >= 1 && s.length <= 40 && !/^(请选择|选择|更多|查看全部)$/i.test(s) && !out.includes(s)) out.push(s);
    };
    lines.forEach((l, i) => {
      if (/(颜色分类|颜色|款式|型号|规格选择|可选|option|variant)/i.test(l)) {
        const after = l.split(/[:：]/).slice(1).join(':');
        if (after) after.split(/[、|/，,]/).forEach(add);
        for (let j = 1; j <= 5 && i + j < lines.length; j++) {
          const n = lines[i+j];
          if (n.length > 70 || /[¥￥]\s*\d/.test(n)) break;
          if (/^[-*•]\s*/.test(n) || n.length < 35) add(n.replace(/^[-*•]\s*/, ''));
        }
      }
    });
    return out.slice(0, 16);
  }

  function extractSpecs(lines) {
    const specs = [];
    const known = /(品牌|型号|材质|尺寸|重量|产地|适用|兼容|风格|功能|货号|类型|brand|model|material|size|weight|origin|compatib|function)/i;
    for (const l of lines) {
      const m = cleanText(l, 160).match(/^([^:：]{1,28})[:：]\s*(.{1,100})$/);
      if (!m || !known.test(m[1])) continue;
      const pair = [cleanText(m[1], 28), cleanText(m[2], 100)];
      if (pair[0] && pair[1] && !specs.some(x => x[0] === pair[0] && x[1] === pair[1])) specs.push(pair);
      if (specs.length >= 12) break;
    }
    return specs;
  }

  function parseFullReader(text, url) {
    const raw = String(text || '');
    const lines = raw.split('\n').map(x => x.trim()).filter(Boolean);
    if (!raw || raw.length < 80) throw new Error('No public product data returned');
    if (BAD_LINE.test(raw) && raw.length < 1400) throw new Error('Taobao requires verification');

    const title = extractTitle(lines);
    const images = extractImages(raw);
    const price = priceFromLines(lines);
    const seller = firstMatching(lines, /(店铺|店名|商家|seller|store)/i);
    const sales = firstMatching(lines, /(已售|销量|付款人数|人付款|sold|orders?)/i, 90);
    const rating = firstMatching(lines, /(好评率|店铺评分|rating|positive rate|positive)/i, 90);
    const reviews = firstMatching(lines, /(累计评价|评价\s*\d|评论|reviews?)/i, 90);
    const shipping = firstMatching(lines, /(运费|配送|发货|物流|送达|shipping|delivery)/i, 140);
    const variants = extractVariants(lines);
    const specs = extractSpecs(lines);
    const descLines = lines
      .map(x => cleanText(x, 220))
      .filter(x => x.length > 12 && !NAV_NOISE.test(x) && !/^title\s*:/i.test(x) && !/^url source:/i.test(x) && !/^!\[/.test(x))
      .slice(0, 10);

    return {
      title: title || 'Imported Taobao product',
      costCny: price,
      images,
      seller,
      sales,
      rating,
      reviews,
      shipping,
      variants,
      specs,
      source: url,
      description: descLines.join(' ').slice(0, 900),
    };
  }

  function quality(d) {
    return (d.title && !/^Imported Taobao product$/i.test(d.title) ? 4 : 0)
      + (d.costCny > 0 ? 5 : 0)
      + Math.min(6, (d.images || []).length)
      + (d.seller ? 1 : 0) + (d.sales ? 1 : 0) + (d.rating ? 1 : 0)
      + Math.min(3, (d.variants || []).length) + Math.min(3, (d.specs || []).length);
  }

  function mergeData(base, next) {
    const pick = (a,b) => a || b || '';
    return {
      title: pick(base.title && base.title !== 'Imported Taobao product' ? base.title : '', next.title),
      costCny: base.costCny || next.costCny || 0,
      images: uniq([...(base.images || []), ...(next.images || [])]).slice(0, MAX_IMAGES),
      seller: pick(base.seller, next.seller),
      sales: pick(base.sales, next.sales),
      rating: pick(base.rating, next.rating),
      reviews: pick(base.reviews, next.reviews),
      shipping: pick(base.shipping, next.shipping),
      variants: uniq([...(base.variants || []), ...(next.variants || [])]).slice(0, 16),
      specs: [...(base.specs || []), ...(next.specs || [])].filter((x,i,a) => a.findIndex(y => y[0]===x[0] && y[1]===x[1]) === i).slice(0,12),
      source: base.source || next.source,
      description: (base.description && base.description.length >= next.description?.length ? base.description : next.description) || '',
    };
  }

  async function fetchReader(url, signal) {
    const reader = 'https://r.jina.ai/' + url;
    const r = await fetch(reader, { signal, headers: { Accept: 'text/plain' }, cache: 'no-store' });
    if (!r.ok) throw new Error('Public reader returned ' + r.status);
    return await r.text();
  }

  window.parseReader = parseFullReader;
  window.importPublic = async function(url) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 24000);
    let best = null;
    let lastError = null;
    try {
      const urls = candidateUrls(url);
      for (const candidate of urls) {
        try {
          const text = await fetchReader(candidate, controller.signal);
          const d = parseFullReader(text, url);
          best = best ? mergeData(best, d) : d;
          if (quality(best) >= 13 && best.costCny > 0 && best.images.length >= 2) break;
        } catch (e) { lastError = e; }
      }
      if (!best) throw lastError || new Error('Import failed');
      if (!best.costCny && !(best.images || []).length) throw new Error('Price and pictures were not publicly available');
      return best;
    } finally { clearTimeout(timer); }
  };

  const btn = document.getElementById('importBtn');
  if (btn) btn.textContent = 'Import price + pictures';
  const input = document.getElementById('taobaoInput');
  if (input) input.placeholder = 'Paste Taobao/Tmall product link here — price and pictures will be imported automatically when public…';

  console.info('Cambodia Product Studio importer v3 loaded');
})();
