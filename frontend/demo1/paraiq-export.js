/* ═══════════════════════════════════════════════════════════
   paraiq-export.js  —  ParaIQ Session 5: Unified PDF Export
   Shared frontend utility for all module export buttons.

   Usage (per page):
     ParaIQExport.download({
       module: 'credibility',
       title:  'Credibility Report',
       sections: [ ... ]
     });

   Or use the auto-packager for standard result containers:
     ParaIQExport.autoExport('credibility', 'Credibility Report');
═══════════════════════════════════════════════════════════ */

var ParaIQExport = (function () {

  /* ── Config ─────────────────────────────────────────── */
  var API = 'https://nlp.para-iq.com';

  /* Resolve API key — tries multiple locations pages might use */
  function getApiKey() {
    if (typeof API_KEY !== 'undefined' && API_KEY) return API_KEY;
    if (typeof PARAIQ_KEY !== 'undefined' && PARAIQ_KEY) return PARAIQ_KEY;
    try { return localStorage.getItem('paraiq_api_key') || ''; } catch (e) {}
    return '';
  }

  /* ── Button state helpers ───────────────────────────── */
  function setBtnLoading(btn) {
    if (!btn) return;
    btn._origText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '⏳ Generating PDF…';
  }

  function resetBtn(btn) {
    if (!btn) return;
    btn.disabled = false;
    btn.innerHTML = btn._origText || '📄 Export PDF';
  }

  /* ── Core download ──────────────────────────────────── */
  async function download(config, btnEl) {
    var btn = btnEl || document.getElementById('paraiq-export-btn');
    setBtnLoading(btn);

    try {
      var resp = await fetch(API + '/export/module', {
        method:  'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key':    getApiKey()
        },
        body: JSON.stringify(config)
      });

      if (!resp.ok) {
        var err = await resp.text();
        throw new Error('Server error: ' + err);
      }

      var blob = await resp.blob();
      var url  = URL.createObjectURL(blob);
      var a    = document.createElement('a');
      a.href   = url;
      a.download = (config.filename ||
        config.module + '_report_' + new Date().toISOString().slice(0, 10) + '.pdf');
      document.body.appendChild(a);
      a.click();
      setTimeout(function () {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 500);

    } catch (e) {
      console.error('[ParaIQExport]', e);
      alert('PDF export failed: ' + e.message);
    } finally {
      resetBtn(btn);
    }
  }

  /* ── DOM helpers ────────────────────────────────────── */

  /** Extract rows from an HTML table element */
  function tableToRows(tbl) {
    if (!tbl) return { headers: [], rows: [] };
    var allRows = Array.from(tbl.querySelectorAll('tr'));
    if (allRows.length === 0) return { headers: [], rows: [] };
    var headers = Array.from(allRows[0].querySelectorAll('th,td'))
                       .map(function (c) { return c.innerText.trim(); });
    var rows = allRows.slice(1).map(function (tr) {
      return Array.from(tr.querySelectorAll('td,th'))
                  .map(function (c) { return c.innerText.trim(); });
    });
    return { headers: headers, rows: rows };
  }

  /** Convert a results container's DOM into PDF sections */
  function domToSections(containerSel) {
    var container = document.querySelector(containerSel);
    if (!container || container.innerHTML.trim().length < 50) return null;

    var sections = [];

    /* Walk top-level children and group by heading */
    var currentHeading = null;
    var currentItems   = [];

    function flush() {
      if (currentItems.length === 0) return;
      var text = currentItems.join('\n').trim();
      if (text.length > 0) {
        sections.push({ type: 'text', heading: currentHeading, content: text });
      }
      currentItems   = [];
      currentHeading = null;
    }

    function walk(el) {
      var tag = el.tagName ? el.tagName.toLowerCase() : '';

      if (/^h[1-6]$/.test(tag) || el.classList.contains('section-title') ||
          el.classList.contains('card-title') || el.classList.contains('result-card-header')) {
        flush();
        currentHeading = el.innerText.trim();
        return;
      }

      if (tag === 'table') {
        flush();
        var t = tableToRows(el);
        if (t.headers.length > 0) {
          sections.push({ type: 'table', heading: currentHeading, headers: t.headers, rows: t.rows });
          currentHeading = null;
        }
        return;
      }

      if (tag === 'ul' || tag === 'ol') {
        flush();
        var items = Array.from(el.querySelectorAll('li')).map(function (li) {
          return li.innerText.trim();
        }).filter(Boolean);
        if (items.length) {
          sections.push({ type: 'bullets', heading: currentHeading, items: items });
          currentHeading = null;
        }
        return;
      }

      /* Generic text nodes */
      var text = el.innerText ? el.innerText.trim() : '';
      if (text.length > 3) currentItems.push(text);

      /* Recurse into containers */
      if (el.children && el.children.length > 0 &&
          !['p','span','a','strong','em','b','i'].includes(tag)) {
        Array.from(el.children).forEach(walk);
      }
    }

    Array.from(container.children).forEach(walk);
    flush();

    return sections.length > 0 ? sections : null;
  }

  /* ── Auto-export (generic DOM scrape) ───────────────── */
  function autoExport(module, title, btnEl) {
    /* Try known result containers in priority order */
    var selectors = ['#results', '#pdfResults', '#textResults',
                     '.results-grid', '#redactionPanel'];
    var sections = null;
    for (var i = 0; i < selectors.length; i++) {
      sections = domToSections(selectors[i]);
      if (sections) break;
    }

    if (!sections || sections.length === 0) {
      alert('No results to export. Run an analysis first.');
      return;
    }

    download({
      module:    module,
      title:     title,
      subtitle:  new Date().toLocaleDateString('en-US', { year:'numeric', month:'long', day:'numeric' }),
      sections:  sections,
    }, btnEl);
  }

  /* ── Per-module packagers ────────────────────────────── */

  var modules = {

    analyzer: function (btn) {
      var res = document.getElementById('results');
      if (!res || res.style.display === 'none') { alert('Run analysis first.'); return; }
      var sections = [];

      /* Sentiment */
      var sentLabel = (document.querySelector('.s-pill') || {}).textContent || '';
      var barFill   = document.querySelector('.bar-fill');
      var sentPct   = barFill ? barFill.style.width : '';
      var sentExpl  = (document.querySelector('.expl') || {}).textContent || '';
      var tones     = Array.from(document.querySelectorAll('.tone-chip'))
                           .map(function(t){ return t.textContent.trim(); }).filter(Boolean);
      if (sentLabel) {
        sections.push({ type: 'kv', heading: 'Sentiment Analysis', data: [
          ['Sentiment',   sentLabel.toUpperCase()],
          ['Score',       sentPct],
          ['Explanation', sentExpl.trim()],
          ['Tones',       tones.join(', ') || '—'],
        ]});
      }

      /* Named entities */
      var ents = Array.from(document.querySelectorAll('.ent-wrap .ent')).map(function(e) {
        var lbl  = (e.querySelector('.ent-lbl') || {}).textContent || '';
        var conf = e.textContent.match(/\d+%/);
        var name = e.childNodes[0] ? e.childNodes[0].textContent.trim() : e.textContent.trim();
        return (lbl ? '[' + lbl.trim() + '] ' : '') + name + (conf ? ' ' + conf[0] : '');
      }).filter(Boolean);
      if (ents.length) sections.push({ type: 'bullets', heading: 'Named Entities', items: ents });

      /* Key phrases */
      var kws = Array.from(document.querySelectorAll('.kw-wrap .kw'))
                     .map(function(k){ return k.textContent.trim(); }).filter(Boolean);
      if (kws.length) sections.push({ type: 'bullets', heading: 'Key Phrases', items: kws });

      /* Plain language summary */
      var summary = (document.querySelector('.summary-text') || {}).textContent || '';
      if (summary.trim()) sections.push({ type: 'text', heading: 'Plain Language Summary', content: summary.trim() });

      /* Text statistics */
      var statNs = Array.from(document.querySelectorAll('.stats .stat-n'))
                        .map(function(e){ return e.textContent.trim(); });
      var statLs = Array.from(document.querySelectorAll('.stats .stat-l'))
                        .map(function(e){ return e.textContent.trim(); });
      if (statNs.length) {
        sections.push({ type: 'kv', heading: 'Text Statistics',
          data: statNs.map(function(v,i){ return [statLs[i]||'', v]; }) });
      }

      if (!sections.length) { alert('Run analysis first.'); return; }
      download({ module:'analyzer', title:'Text Analysis Report', sections:sections }, btn);
    },

    batch: function (btn) {
      var res = document.getElementById('results');
      if (!res || res.style.display === 'none') { alert('Run batch analysis first.'); return; }
      var sections = [];

      /* Summary stats — total docs, successful, failed, avg sentiment */
      var sumNs = Array.from(document.querySelectorAll('.sum-card .sum-n'))
                       .map(function(e){ return e.textContent.trim(); });
      var sumLs = Array.from(document.querySelectorAll('.sum-card .sum-l'))
                       .map(function(e){ return e.textContent.trim(); });
      if (sumNs.length) {
        sections.push({ type: 'kv', heading: 'Batch Summary',
          data: sumNs.map(function(v,i){ return [sumLs[i]||'', v]; }) });
      }

      /* Document results table — truncate long cells, drop Keywords col */
      var tbl = document.querySelector('.results-table-wrap table');
      if (tbl) {
        var tData = tableToRows(tbl);
        if (tData.headers.length) {
          var keep = [0, 1, 3, 6];  /* # | Label | Sentiment | Summary */
          var hdrs = keep.map(function(i){ return tData.headers[i] || ''; });
          var rows = tData.rows.map(function(row) {
            return keep.map(function(i) {
              var v = (row[i] || '').trim();
              if (i === 6 && v.length > 150) v = v.slice(0, 150) + '…';
              return v;
            });
          });
          sections.push({ type: 'table', heading: 'Document Results',
            headers: hdrs, rows: rows,
            col_widths_in: [0.25, 1.3, 1.25, 3.5] });  /* 6.3" total */
        }
      }

      if (!sections.length) { alert('Run batch analysis first.'); return; }
      download({ module:'batch', title:'Batch Analysis Report', sections:sections }, btn);
    },

    timeline: function (btn) {
      var res = document.getElementById('results');
      if (!res || res.style.display === 'none') { alert('Generate a timeline first.'); return; }
      var sections = [];

      /* Event count stats */
      var statNs = Array.from(document.querySelectorAll('.stats-row .stat-n'))
                        .map(function(e){ return e.textContent.trim(); });
      var statLs = Array.from(document.querySelectorAll('.stats-row .stat-l'))
                        .map(function(e){ return e.textContent.trim(); });
      if (statNs.length) {
        sections.push({ type: 'kv', heading: 'Timeline Summary',
          data: statNs.map(function(v,i){ return [statLs[i]||'', v]; }) });
      }

      /* Document info + key parties */
      var docTitle  = (document.querySelector('.doc-title')  || {}).textContent || '';
      var metaItems = Array.from(document.querySelectorAll('.meta-item'))
                           .map(function(m){ return m.textContent.trim(); });
      var parties   = Array.from(document.querySelectorAll('.party-chip'))
                           .map(function(p){ return p.textContent.trim(); }).filter(Boolean);
      var docData   = [];
      if (docTitle) docData.push(['Document', docTitle]);
      metaItems.forEach(function(m) {
        var idx = m.indexOf(':');
        if (idx > 0) docData.push([m.slice(0,idx).trim(), m.slice(idx+1).trim()]);
      });
      if (parties.length) docData.push(['Key Parties', parties.join(', ')]);
      if (docData.length) sections.push({ type: 'kv', heading: 'Document Info', data: docData });

      /* Chronological events — date: description [category] — amount (parties) */
      var events = Array.from(document.querySelectorAll('.timeline .event')).map(function(ev) {
        var date  = (ev.querySelector('.event-date')    || {}).textContent || '';
        var text  = (ev.querySelector('.event-text')    || {}).textContent || '';
        var cat   = (ev.querySelector('.cat-badge')     || {}).textContent || '';
        var amt   = (ev.querySelector('.event-amount')  || {}).textContent || '';
        var parts = (ev.querySelector('.event-parties') || {}).textContent || '';
        var line  = (date ? date.trim() + ': ' : '') + text.trim();
        if (cat.trim())   line += '  [' + cat.trim() + ']';
        if (amt.trim())   line += '  — ' + amt.trim();
        if (parts.trim()) line += '  (' + parts.trim() + ')';
        return line;
      }).filter(Boolean);
      if (events.length) sections.push({ type: 'bullets', heading: 'Chronological Events', items: events });

      if (!sections.length) { alert('Generate a timeline first.'); return; }
      download({ module:'timeline', title:'Legal Event Timeline', sections:sections }, btn);
    },

    citations: function (btn) {
      var summGrid = document.getElementById('summaryGrid');
      var citList  = document.getElementById('citationsList');
      if (!summGrid || !citList) { alert('Run citation extraction first.'); return; }
      var sections = [];

      /* Citation summary stats */
      var sumNs = Array.from(document.querySelectorAll('#summaryGrid .sum-n'))
                       .map(function(e){ return e.textContent.trim(); });
      var sumLs = Array.from(document.querySelectorAll('#summaryGrid .sum-l'))
                       .map(function(e){ return e.textContent.trim(); });
      if (sumNs.length && sumNs.some(function(v){ return v !== '0'; })) {
        sections.push({ type: 'kv', heading: 'Citation Summary',
          data: sumNs.map(function(v,i){ return [sumLs[i]||'', v]; }) });
      }

      /* Individual citations — raw text + type + resolved match */
      var items = Array.from(document.querySelectorAll('#citationsList .citation-item'))
        .map(function(el) {
          var raw      = (el.querySelector('.citation-raw')  || {}).textContent || '';
          var type     = (el.querySelector('.citation-type') || {}).textContent || '';
          var resolved = (el.querySelector('.resolved-name') || {}).textContent || '';
          var meta     = (el.querySelector('.resolved-meta') || {}).textContent || '';
          var line = (type.trim() ? '[' + type.trim() + '] ' : '') + raw.trim();
          if (resolved.trim()) line += ' → ' + resolved.trim();
          if (meta.trim())     line += ' (' + meta.trim() + ')';
          return line;
        }).filter(Boolean);
      if (items.length) sections.push({ type: 'bullets', heading: 'Extracted Citations', items: items });

      if (!sections.length) { alert('Run citation extraction first.'); return; }
      download({ module:'citations', title:'Citation Resolution Report', sections:sections }, btn);
    },

    compare: function (btn) {
      /* Read structured data from specific DOM elements */
      var sections = [];

      /* 1. Similarity Scores */
      var cosine   = (document.getElementById('cosineScore')   || {}).textContent || '';
      var jaccard  = (document.getElementById('jaccardScore')  || {}).textContent || '';
      var combined = (document.getElementById('combinedScore') || {}).textContent || '';
      var simLabel = (document.getElementById('simLabel')      || {}).textContent || '';
      if (cosine) {
        sections.push({ type: 'kv', heading: 'Similarity Scores', data: [
          ['Cosine (TF-IDF)', cosine],
          ['Jaccard (Terms)', jaccard],
          ['Combined Score',  combined],
          ['Assessment',      simLabel.toUpperCase()],
        ]});
      }

      /* 2. Entity Overlap */
      var overlapScore = (document.getElementById('overlapScore') || {}).textContent || '';
      var shared = Array.from(document.querySelectorAll('#sharedEnts .tag')).map(function(e){ return e.textContent.trim(); });
      var onlyA  = Array.from(document.querySelectorAll('#onlyA .tag')).map(function(e){ return e.textContent.trim(); });
      var onlyB  = Array.from(document.querySelectorAll('#onlyB .tag')).map(function(e){ return e.textContent.trim(); });
      if (overlapScore) {
        sections.push({ type: 'kv', heading: 'Entity Overlap', data: [
          ['Overlap Score', overlapScore],
          ['Shared Entities', shared.length ? shared.join(', ') : 'None'],
          ['Only in Document A', onlyA.length ? onlyA.join(', ') : 'None'],
          ['Only in Document B', onlyB.length ? onlyB.join(', ') : 'None'],
        ]});
      }

      /* 3. Citation Diff */
      var citEl = document.getElementById('citationDiff');
      if (citEl && citEl.innerText.trim()) {
        sections.push({ type: 'text', heading: 'Citation Diff', content: citEl.innerText.trim() });
      }

      /* 4. Structural Comparison — read table cells */
      var structEl = document.getElementById('structGrid');
      if (structEl) {
        var cells = Array.from(structEl.querySelectorAll('.struct-cell')).map(function(c){ return c.innerText.trim(); });
        // cells layout: [METRIC, DOC A, DOC B, Words, val, val, Sentences, val, val, ...]
        var structRows = [];
        var i = 3; // skip header row (3 cells)
        while (i + 2 < cells.length) {
          structRows.push([cells[i], cells[i+1], cells[i+2]]);
          i += 3;
        }
        if (structRows.length) {
          sections.push({ type: 'table', heading: 'Structural Comparison',
            headers: ['Metric', 'Document A', 'Document B'],
            rows: structRows,
            col_widths_in: [2.5, 1.9, 1.9]
          });
        }
      }

      /* 5. Lease Clause Analysis (if visible) */
      var leaseCard = document.getElementById('leaseCard');
      if (leaseCard && leaseCard.style.display !== 'none') {
        var keyTerms = Array.from(document.querySelectorAll('#leaseKeyTerms .lease-tag')).map(function(e){ return e.textContent.trim(); });
        var modified = Array.from(document.querySelectorAll('#leaseModified .clause-item')).map(function(e){ return e.innerText.trim(); });
        var added    = Array.from(document.querySelectorAll('#leaseAdded .clause-item')).map(function(e){ return e.innerText.trim(); });
        var removed  = Array.from(document.querySelectorAll('#leaseRemoved .clause-item')).map(function(e){ return e.innerText.trim(); });
        if (keyTerms.length || modified.length) {
          if (keyTerms.length) sections.push({ type: 'bullets', heading: 'Lease Key Term Changes', items: keyTerms });
          if (modified.length) sections.push({ type: 'bullets', heading: 'Modified Clauses', items: modified });
          if (added.length)    sections.push({ type: 'bullets', heading: 'Added Clauses',    items: added });
          if (removed.length)  sections.push({ type: 'bullets', heading: 'Removed Clauses',  items: removed });
        }
      }

      if (!sections.length) { alert('Run document comparison first.'); return; }
      download({ module:'compare', title:'Document Comparison Report', sections:sections }, btn);
    },

    credibility: function (btn) {
      /* Credibility has radar chart + dimension scores */
      var sections = domToSections('#results');
      /* Also try to capture dimension table if separate */
      var extra = domToSections('.radar-labels') || domToSections('.dimension-scores');
      if (extra) sections = (sections || []).concat(extra);
      if (!sections || sections.length === 0) { alert('Score a witness first.'); return; }
      download({ module:'credibility', title:'Witness Credibility Report', sections:sections }, btn);
    },

    deposition: function (btn) {
      var sections = domToSections('#results');
      if (!sections) { alert('Generate a deposition summary first.'); return; }
      download({ module:'deposition', title:'Deposition Summary Report', sections:sections }, btn);
    },

    scorer: function (btn) {
      var ct = document.getElementById('manualResults') || document.getElementById('autoResults');
      if (!ct || ct.innerHTML.trim().length < 50) { alert('Run scoring first.'); return; }
      var sections = [];

      /* Overall score + verdict */
      var f1      = (ct.querySelector('.score-n') || {}).textContent || '';
      var heroR   = ct.querySelector('.score-hero > div:last-child') || ct.querySelector('.score-hero > div:nth-child(2)');
      var verdict = heroR ? ((heroR.querySelector('div') || {}).textContent || '').trim() : '';
      var pills   = Array.from(ct.querySelectorAll('.score-hero > div:last-child span'))
                        .map(function(s){ return s.textContent.trim(); })
                        .filter(function(s){ return s.length > 2; });
      var hallRisk = '', compression = '';
      pills.forEach(function(p) {
        if (p.toLowerCase().includes('hallucination')) hallRisk   = p;
        if (p.toLowerCase().includes('compression'))   compression = p;
      });
      if (f1) {
        var kvData = [['F1 Score', f1.trim() + '%'], ['Verdict', verdict]];
        if (hallRisk)   kvData.push(['Hallucination Risk', hallRisk]);
        if (compression) kvData.push(['Compression Ratio', compression]);
        sections.push({ type: 'kv', heading: 'Overall Quality Score', data: kvData });
      }

      /* Primary metrics — Precision, Recall, F1 */
      var metrics = Array.from(ct.querySelectorAll('.metric-box')).map(function(box) {
        var val  = (box.querySelector('.metric-n') || {}).textContent || '';
        var lbl  = (box.querySelector('.metric-l') || {}).textContent || '';
        var desc = Array.from(box.querySelectorAll('div')).pop();
        var note = desc ? desc.textContent.trim() : '';
        return lbl.trim() + ': ' + val.trim() + (note ? ' (' + note + ')' : '');
      }).filter(Boolean);
      if (metrics.length) sections.push({ type: 'bullets', heading: 'Scoring Metrics', items: metrics });

      /* Sub-scores — factual accuracy, completeness, conciseness, fluency */
      var subEl = ct.querySelector('.sub-scores');
      if (subEl) {
        var subTokens = subEl.textContent.split('\n')
          .map(function(s){ return s.trim(); }).filter(Boolean);
        var subData = [];
        for (var si = 0; si < subTokens.length - 1; si++) {
          var nxt = subTokens[si + 1];
          if (nxt && (nxt.includes('%') || /^\d/.test(nxt))) {
            subData.push([subTokens[si], nxt]); si++;
          }
        }
        if (subData.length) sections.push({ type: 'kv', heading: 'Sub-Scores', data: subData });
      }

      /* Coverage analysis */
      var cards = Array.from(ct.querySelectorAll('.card'));
      var covCard = cards.find(function(c){
        return ((c.querySelector('.card-title')||{}).textContent||'').includes('Coverage');
      });
      if (covCard) {
        var covText = covCard.textContent.replace('Coverage analysis','').trim();
        if (covText) sections.push({ type: 'text', heading: 'Coverage Analysis', content: covText });
      }

      /* Feedback + improvement */
      var fb  = (ct.querySelector('.feedback-box')    || {}).textContent || '';
      var imp = (ct.querySelector('.improvement-box') || {}).textContent || '';
      if (fb.trim())  sections.push({ type: 'text', heading: 'Feedback',              content: fb.trim() });
      if (imp.trim()) sections.push({ type: 'text', heading: 'Improvement Suggestion', content: imp.trim() });

      /* Meta */
      var meta = (ct.querySelector('.meta-row') || {}).textContent || '';
      if (meta.trim()) sections.push({ type: 'text', heading: 'Analysis Details', content: meta.trim() });

      if (!sections.length) { alert('Run scoring first.'); return; }
      download({ module:'scorer', title:'NLP Scoring Report', sections:sections }, btn);
    },

    audit: function (btn) {
      var sections = [];
      var total   = (document.getElementById('kpiTotal')   || {}).textContent || '';
      var success = (document.getElementById('kpiSuccess') || {}).textContent || '';
      var errors  = (document.getElementById('kpiErrors')  || {}).textContent || '';
      var avgMs   = (document.getElementById('kpiAvgMs')   || {}).textContent || '';
      if (total) {
        sections.push({ type: 'kv', heading: 'API Audit Summary', data: [
          ['Total Requests',    total],
          ['Successful (2xx)',  success],
          ['Errors',            errors],
          ['Avg Response (ms)', avgMs],
        ]});
      }
      var epTbl = document.getElementById('endpointTable');
      if (epTbl) {
        var tData = tableToRows(epTbl);
        if (tData.headers.length) {
          sections.push({ type: 'table', heading: 'Top Endpoints',
            headers: tData.headers, rows: tData.rows });
        }
      }
      if (!sections.length) { alert('Load audit data first.'); return; }
      download({ module:'audit', title:'Audit Trail Report', sections:sections }, btn);
    },

    multilingual: function (btn) {
      var sections = domToSections('#results');
      if (!sections) { alert('Run multilingual analysis first.'); return; }
      download({ module:'multilingual', title:'Multilingual NLP Report', sections:sections }, btn);
    },

    review: function (btn) {
      var sections = domToSections('#results');
      if (!sections) { alert('Complete document review first.'); return; }
      download({ module:'review', title:'Document Review Report', sections:sections }, btn);
    },

    risk: function (btn) {
      var res = document.getElementById('results');
      if (!res || res.style.display === 'none') { alert('Run risk scoring first.'); return; }
      var sections = [];
      var score = (document.getElementById('scoreNum')  || {}).textContent || '';
      var level = (document.getElementById('riskLevel') || {}).textContent || '';
      if (score) {
        sections.push({ type: 'kv', heading: 'Risk Assessment', data: [
          ['Risk Score', score.trim() + ' / 10'],
          ['Risk Level', level.trim()],
        ]});
      }
      var bd = domToSections('#breakdown');   if (bd)   sections = sections.concat(bd);
      var sg = domToSections('#signals');     if (sg)   sections = sections.concat(sg);
      var mt = domToSections('#mitigations'); if (mt)   sections = sections.concat(mt);
      if (!sections.length) { alert('Run risk scoring first.'); return; }
      download({ module:'risk', title:'Risk Assessment Report', sections:sections }, btn);
    },

    redaction: function (btn) {
      var sections = [];

      /* ── Text Redaction tab ── */
      var total      = (document.getElementById('statTotal')      || {}).textContent || '';
      var categories = (document.getElementById('statCategories') || {}).textContent || '';
      var confidence = (document.getElementById('statConfidence') || {}).textContent || '';
      var claude     = (document.getElementById('statClaude')     || {}).textContent || '';
      var original   = (document.getElementById('originalText')   || {}).textContent || '';
      var redacted   = (document.getElementById('redactedText')   || {}).textContent || '';

      if (total && total !== '0') {
        sections.push({ type: 'kv', heading: 'Redaction Summary', data: [
          ['Total Redactions',   total],
          ['Categories Found',   categories],
          ['Avg Confidence',     confidence],
          ['Claude AI Catches',  claude],
        ]});
        if (original) sections.push({ type: 'text', heading: 'Original Text',  content: original });
        if (redacted) sections.push({ type: 'text', heading: 'Redacted Output', content: redacted });

        /* Findings list */
        var findingsEl = document.getElementById('findingsList');
        if (findingsEl) {
          var items = Array.from(findingsEl.querySelectorAll('.finding-item, [class*="finding"]'))
            .map(function(el) { return el.innerText.trim(); }).filter(Boolean);
          if (items.length) sections.push({ type: 'bullets', heading: 'Detected Entities', items: items });
        }
      }

      /* ── PDF Redaction tab fallback ── */
      if (sections.length === 0) {
        var pdfTotal = (document.getElementById('pdfStatTotal') || {}).textContent || '';
        var pdfPages = (document.getElementById('pdfStatPages') || {}).textContent || '';
        var pdfCats  = (document.getElementById('pdfStatCategories') || {}).textContent || '';
        var pdfConf  = (document.getElementById('pdfStatConfidence') || {}).textContent || '';
        if (pdfTotal && pdfTotal !== '0') {
          sections.push({ type: 'kv', heading: 'PDF Redaction Summary', data: [
            ['Total Redactions', pdfTotal],
            ['Pages Processed',  pdfPages],
            ['Categories Found', pdfCats],
            ['Avg Confidence',   pdfConf],
          ]});
          var pdfOrig = domToSections('#pdfResults');
          if (pdfOrig) sections = sections.concat(pdfOrig);
        }
      }

      if (!sections.length) { alert('Run redaction first, then export.'); return; }
      download({ module:'redaction', title:'Redaction Report', sections:sections }, btn);
    },

    redaction_review: function (btn) {
      var sections = domToSections('#results') || domToSections('#redactionPanel');
      if (!sections) { alert('Load redaction review first.'); return; }
      download({ module:'redaction_review', title:'Redaction Review Report', sections:sections }, btn);
    },

  };

  /* ── Inject export button ───────────────────────────── */

  function injectButton(module, label) {
    if (document.getElementById('paraiq-export-btn')) return;

    var btn = document.createElement('button');
    btn.id          = 'paraiq-export-btn';
    btn.innerHTML   = '📄 ' + (label || 'Export PDF');
    btn.title       = 'Download results as PDF';
    btn.onclick     = function () {
      if (modules[module]) {
        modules[module](btn);
      } else {
        autoExport(module, label || 'Report', btn);
      }
    };

    /* Style — matches ParaIQ button aesthetic */
    var s = btn.style;
    s.position       = 'fixed';
    s.bottom         = '24px';
    s.right          = '24px';
    s.zIndex         = '8888';
    s.background     = '#7c3aed';
    s.color          = '#fff';
    s.border         = 'none';
    s.borderRadius   = '10px';
    s.padding        = '10px 18px';
    s.fontSize       = '13px';
    s.fontWeight     = '600';
    s.cursor         = 'pointer';
    s.boxShadow      = '0 4px 16px rgba(124,58,237,0.4)';
    s.fontFamily     = '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    s.transition     = 'background 0.15s, transform 0.1s';

    btn.addEventListener('mouseover',  function () { s.background = '#6d28d9'; });
    btn.addEventListener('mouseout',   function () { s.background = '#7c3aed'; });
    btn.addEventListener('mousedown',  function () { s.transform  = 'scale(0.97)'; });
    btn.addEventListener('mouseup',    function () { s.transform  = 'scale(1)'; });

    document.body.appendChild(btn);
  }

  /* ── Public API ─────────────────────────────────────── */
  return {
    download:     download,
    autoExport:   autoExport,
    injectButton: injectButton,
    modules:      modules,
    domToSections: domToSections,
  };

})();
