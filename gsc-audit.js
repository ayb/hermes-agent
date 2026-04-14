const { google } = require('googleapis');
const fs = require('fs');

// Load credentials from env
const clientEmail = process.env.GSC_SERVICE_ACCOUNT_EMAIL?.trim();
const privateKey = process.env.GSC_PRIVATE_KEY?.replace(/\\n/g, '\n');
const siteUrl = process.env.GSC_SITE_URL;

if (!clientEmail || !privateKey || !siteUrl) {
  console.error('Missing GSC credentials');
  process.exit(1);
}

async function getClient() {
  const auth = new google.auth.GoogleAuth({
    credentials: {
      client_email: clientEmail,
      private_key: privateKey,
    },
    scopes: ['https://www.googleapis.com/auth/webmasters.readonly'],
  });
  const authClient = await auth.getClient();
  return google.searchconsole({ version: 'v1', auth: authClient });
}

function formatDate(d) {
  return d.toISOString().split('T')[0];
}

function getPeriods() {
  const today = new Date();
  const todayStr = formatDate(today);
  
  // Current period: last 90 days
  const currentStart = new Date(today);
  currentStart.setDate(currentStart.getDate() - 90);
  const currentStartStr = formatDate(currentStart);
  
  // Previous period: 90 days before that
  const prevEnd = new Date(currentStart);
  prevEnd.setDate(prevEnd.getDate() - 1);
  const prevEndStr = formatDate(prevEnd);
  const prevStart = new Date(prevEnd);
  prevStart.setDate(prevStart.getDate() - 90);
  const prevStartStr = formatDate(prevStart);
  
  return {
    current: { start: currentStartStr, end: todayStr },
    previous: { start: prevStartStr, end: prevEndStr }
  };
}

async function runAudit() {
  const searchconsole = await getClient();
  const periods = getPeriods();
  
  console.log('=== GSC Audit for', siteUrl, '===');
  console.log('Current period:', periods.current.start, 'to', periods.current.end);
  console.log('Previous period:', periods.previous.start, 'to', periods.previous.end);
  console.log('');
  
  // 1. Site-wide metrics - current period
  const currentMetrics = await searchconsole.searchanalytics.query({
    siteUrl: siteUrl,
    requestBody: {
      startDate: periods.current.start,
      endDate: periods.current.end,
      dimensions: [],
    }
  });
  
  const current = currentMetrics.data.rows?.[0] || { clicks: 0, impressions: 0, ctr: 0, position: 0 };
  
  // Previous period
  const prevMetrics = await searchconsole.searchanalytics.query({
    siteUrl: siteUrl,
    requestBody: {
      startDate: periods.previous.start,
      endDate: periods.previous.end,
      dimensions: [],
    }
  });
  
  const previous = prevMetrics.data.rows?.[0] || { clicks: 0, impressions: 0, ctr: 0, position: 0 };
  
  console.log('=== SITE-WIDE METRICS ===');
  console.log('Metric          | Current     | Previous    | Change %');
  console.log('----------------|-------------|-------------|---------');
  console.log(`Clicks          | ${current.clicks.toLocaleString().padEnd(11)} | ${previous.clicks.toLocaleString().padEnd(11)} | ${(((current.clicks - previous.clicks) / (previous.clicks || 1) * 100).toFixed(1) + '%').padEnd(8)}`);
  console.log(`Impressions     | ${current.impressions.toLocaleString().padEnd(11)} | ${previous.impressions.toLocaleString().padEnd(11)} | ${(((current.impressions - previous.impressions) / (previous.impressions || 1) * 100).toFixed(1) + '%').padEnd(8)}`);
  console.log(`CTR             | ${(current.ctr * 100).toFixed(2) + '%'.padEnd(10)} | ${(previous.ctr * 100).toFixed(2) + '%'.padEnd(10)} | ${((current.ctr - previous.ctr) * 100).toFixed(2) + 'pp'}`);
  console.log(`Avg Position    | ${current.position.toFixed(1).padEnd(11)} | ${previous.position.toFixed(1).padEnd(11)} | ${(current.position - previous.position).toFixed(1)}`);
  console.log('');
  
  // 2. Top Pages
  const pagesData = await searchconsole.searchanalytics.query({
    siteUrl: siteUrl,
    requestBody: {
      startDate: periods.current.start,
      endDate: periods.current.end,
      dimensions: ['page'],
      rowLimit: 25,
    }
  });
  
  const prevPagesData = await searchconsole.searchanalytics.query({
    siteUrl: siteUrl,
    requestBody: {
      startDate: periods.previous.start,
      endDate: periods.previous.end,
      dimensions: ['page'],
      rowLimit: 5000,
    }
  });
  
  const prevPagesMap = new Map();
  if (prevPagesData.data.rows) {
    for (const row of prevPagesData.data.rows) {
      prevPagesMap.set(row.keys[0], row);
    }
  }
  
  console.log('=== TOP 20 PAGES (Current vs Previous) ===');
  console.log('Page | Clicks | Prev Clicks | Δ Clicks | Δ % | CTR');
  console.log('-----|--------|-------------|----------|-----|-----');
  const topPages = (pagesData.data.rows || []).slice(0, 20);
  topPages.forEach(row => {
    const page = row.keys[0];
    const prevRow = prevPagesMap.get(page);
    const prevClicks = prevRow ? prevRow.clicks : 0;
    const delta = row.clicks - prevClicks;
    const deltaPct = prevClicks > 0 ? ((delta / prevClicks) * 100).toFixed(0) : 'N/A';
    const shortPage = page.replace(siteUrl, '').substring(0, 35).padEnd(35);
    console.log(`${shortPage} | ${row.clicks} | ${prevClicks} | ${delta > 0 ? '+' : ''}${delta} | ${deltaPct}% | ${(row.ctr * 100).toFixed(2)}%`);
  });
  console.log('');
  
  // 3. Biggest Losers and Winners
  const allCurrentPages = pagesData.data.rows || [];
  const pageChanges = allCurrentPages.map(row => {
    const page = row.keys[0];
    const prevRow = prevPagesMap.get(page);
    const prevClicks = prevRow ? prevRow.clicks : 0;
    return { page, current: row.clicks, previous: prevClicks, delta: row.clicks - prevClicks };
  });
  
  // Also find pages that existed in previous but not in current or with lost traffic
  const currentPagesSet = new Set(allCurrentPages.map(r => r.keys[0]));
  const disappearedPages = [];
  if (prevPagesData.data.rows) {
    for (const prevRow of prevPagesData.data.rows) {
      const page = prevRow.keys[0];
      if (!currentPagesSet.has(page) && prevRow.clicks > 0) {
        disappearedPages.push({ page, current: 0, previous: prevRow.clicks, delta: -prevRow.clicks });
      }
    }
  }
  
  const allChanges = [...pageChanges, ...disappearedPages];
  const losers = allChanges.filter(p => p.delta < 0).sort((a, b) => a.delta - b.delta).slice(0, 10);
  const winners = allChanges.filter(p => p.delta > 0).sort((a, b) => b.delta - a.delta).slice(0, 10);
  
  console.log('=== BIGGEST LOSERS (Top 10) ===');
  losers.forEach(p => {
    const shortPage = p.page.replace(siteUrl, '').substring(0, 40);
    console.log(`${shortPage}: ${p.previous} → ${p.current} clicks (${p.delta})`);
  });
  console.log('');
  
  console.log('=== BIGGEST WINNERS (Top 10) ===');
  winners.forEach(p => {
    const shortPage = p.page.replace(siteUrl, '').substring(0, 40);
    console.log(`${shortPage}: ${p.previous} → ${p.current} clicks (+${p.delta})`);
  });
  console.log('');
  
  // 4. Top Keywords
  const keywordsData = await searchconsole.searchanalytics.query({
    siteUrl: siteUrl,
    requestBody: {
      startDate: periods.current.start,
      endDate: periods.current.end,
      dimensions: ['query'],
      rowLimit: 30,
    }
  });
  
  console.log('=== TOP 30 KEYWORDS BY IMPRESSIONS ===');
  console.log('Keyword | Impressions | Clicks | CTR | Position');
  console.log('--------|-------------|--------|-----|----------');
  const topKeywords = (keywordsData.data.rows || []).sort((a, b) => b.impressions - a.impressions);
  topKeywords.forEach(row => {
    const keyword = row.keys[0].substring(0, 30).padEnd(30);
    console.log(`${keyword} | ${row.impressions.toLocaleString().padEnd(11)} | ${row.clicks.toLocaleString().padEnd(6)} | ${(row.ctr * 100).toFixed(2)}% | ${row.position.toFixed(1)}`);
  });
  console.log('');
  
  // 5. Striking Distance Keywords (positions 11-20, 100+ impressions)
  const strikingData = await searchconsole.searchanalytics.query({
    siteUrl: siteUrl,
    requestBody: {
      startDate: periods.current.start,
      endDate: periods.current.end,
      dimensions: ['query'],
      rowLimit: 5000,
    }
  });
  
  const striking = (strikingData.data.rows || [])
    .filter(row => row.position >= 11 && row.position <= 20 && row.impressions >= 100)
    .sort((a, b) => b.impressions - a.impressions)
    .slice(0, 20);
  
  console.log('=== STRIKING DISTANCE KEYWORDS (Pos 11-20, 100+ impressions) ===');
  console.log('Keyword | Position | Impressions | Clicks | CTR');
  console.log('--------|----------|-------------|--------|-----');
  striking.forEach(row => {
    const keyword = row.keys[0].substring(0, 30).padEnd(30);
    console.log(`${keyword} | ${row.position.toFixed(1).padEnd(8)} | ${row.impressions.toLocaleString().padEnd(11)} | ${row.clicks.toLocaleString().padEnd(6)} | ${(row.ctr * 100).toFixed(2)}%`);
  });
  console.log('');
  
  // 6. Low CTR / High Impression Keywords
  const lowCtr = (strikingData.data.rows || [])
    .filter(row => row.impressions >= 500 && row.ctr < 0.02 && row.position <= 15)
    .sort((a, b) => b.impressions - a.impressions)
    .slice(0, 20);
  
  console.log('=== LOW CTR / HIGH IMPRESSION KEYWORDS (500+ impressions, CTR < 2%, Pos 1-15) ===');
  console.log('Keyword | Position | Impressions | CTR | Expected CTR | Missed Clicks');
  console.log('--------|----------|-------------|-----|--------------|--------------');
  
  // Expected CTR by position
  const expectedCtr = {
    1: 0.133, 2: 0.119, 3: 0.100, 4: 0.081, 5: 0.064,
    6: 0.044, 7: 0.031, 8: 0.024, 9: 0.020, 10: 0.019,
    11: 0.010, 12: 0.009, 13: 0.007, 14: 0.006, 15: 0.005
  };
  
  lowCtr.forEach(row => {
    const pos = Math.round(row.position);
    const expected = expectedCtr[pos] || 0.005;
    const missed = Math.round(row.impressions * (expected - row.ctr));
    const keyword = row.keys[0].substring(0, 30).padEnd(30);
    console.log(`${keyword} | ${row.position.toFixed(1).padEnd(8)} | ${row.impressions.toLocaleString().padEnd(11)} | ${(row.ctr * 100).toFixed(2)}% | ${(expected * 100).toFixed(1)}% | ${missed.toLocaleString()}`);
  });
  console.log('');
  
  // 7. Weekly Traffic Trend
  const weeklyData = await searchconsole.searchanalytics.query({
    siteUrl: siteUrl,
    requestBody: {
      startDate: periods.current.start,
      endDate: periods.current.end,
      dimensions: ['date'],
      rowLimit: 5000,
    }
  });
  
  const weeklyAgg = {};
  (weeklyData.data.rows || []).forEach(row => {
    const date = row.keys[0];
    const week = date.substring(0, 4) + '-W' + getWeekNumber(new Date(date));
    if (!weeklyAgg[week]) weeklyAgg[week] = { clicks: 0, impressions: 0 };
    weeklyAgg[week].clicks += row.clicks;
    weeklyAgg[week].impressions += row.impressions;
  });
  
  console.log('=== WEEKLY TRAFFIC TREND ===');
  console.log('Week | Clicks | Impressions');
  console.log('-----|--------|------------');
  Object.entries(weeklyAgg).sort().forEach(([week, data]) => {
    console.log(`${week} | ${data.clicks.toString().padEnd(6)} | ${data.impressions.toLocaleString()}`);
  });
  console.log('');
  
  // 8. Device Breakdown
  const deviceData = await searchconsole.searchanalytics.query({
    siteUrl: siteUrl,
    requestBody: {
      startDate: periods.current.start,
      endDate: periods.current.end,
      dimensions: ['device'],
    }
  });
  
  console.log('=== DEVICE BREAKDOWN ===');
  console.log('Device | Clicks | Impressions | CTR | Position');
  console.log('-------|--------|-------------|-----|----------');
  (deviceData.data.rows || []).sort((a, b) => b.clicks - a.clicks).forEach(row => {
    const device = row.keys[0].padEnd(6);
    console.log(`${device} | ${row.clicks.toLocaleString().padEnd(6)} | ${row.impressions.toLocaleString().padEnd(11)} | ${(row.ctr * 100).toFixed(2)}% | ${row.position.toFixed(1)}`);
  });
  console.log('');
  
  // 9. Country Breakdown
  const countryData = await searchconsole.searchanalytics.query({
    siteUrl: siteUrl,
    requestBody: {
      startDate: periods.current.start,
      endDate: periods.current.end,
      dimensions: ['country'],
      rowLimit: 15,
    }
  });
  
  console.log('=== TOP COUNTRIES ===');
  console.log('Country | Clicks | Impressions | CTR');
  console.log('--------|--------|-------------|-----');
  (countryData.data.rows || []).sort((a, b) => b.clicks - a.clicks).forEach(row => {
    console.log(`${row.keys[0].padEnd(7)} | ${row.clicks.toLocaleString().padEnd(6)} | ${row.impressions.toLocaleString().padEnd(11)} | ${(row.ctr * 100).toFixed(2)}%`);
  });
  console.log('');
  
  // 10. Disappeared Pages
  if (disappearedPages.length > 0) {
    console.log('=== DISAPPEARED PAGES (had clicks, now zero) ===');
    disappearedPages.slice(0, 15).forEach(p => {
      console.log(`${p.page.replace(siteUrl, '').substring(0, 50)}: lost ${p.previous} clicks`);
    });
  } else {
    console.log('=== DISAPPEARED PAGES ===');
    console.log('No pages with significant traffic loss detected.');
  }
  console.log('');
}

function getWeekNumber(d) {
  d = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  return weekNo.toString().padStart(2, '0');
}

runAudit().catch(err => {
  console.error('Error:', err.message);
  if (err.message.includes('permission') || err.message.includes('does not have')) {
    console.error('\n*** PERMISSION ERROR: The service account needs access to this site in GSC. ***');
    console.error('Add this email to your GSC property:');
    console.error(clientEmail);
  }
  process.exit(1);
});
