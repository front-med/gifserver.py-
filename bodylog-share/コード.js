/**
 * ============================================
 * BODY LOG Share（共有版・マルチユーザー）
 * ============================================
 * 仕組み:
 *  - Web Appを「アクセスしているユーザーとして実行」でデプロイ
 *    → Googleアカウントでのログインが必須（匿名アクセス不可）
 *  - 初回アクセス時に名前を登録（必須）。会員登録の位置づけ
 *  - データは Google ドライブ/スプレッドシートを一切作らず、
 *    GASのユーザープロパティ（このアプリ専用・ユーザーごとに分離された
 *    内部ストレージ）にJSONで保存する
 *    → 要求権限はメールアドレスのみ。登録は名前入力だけで即完了
 *    → 他人のデータは構造上見えない（完全に個人別）
 *  - 共有機能: コンディション記録 / トレーニング記録 / まとめ のみ
 *
 * ストレージ設計（UserProperties、月ごとにチャンク分割）:
 *  - BL_NAME               : 表示名
 *  - BL_EX                 : 種目名のJSON配列
 *  - BL_C_<yyyy-MM>        : { "yyyy-MM-dd": {weight,sleep,fatigue,score,memo,time} }
 *  - BL_T_<yyyy-MM>        : { "yyyy-MM-dd": [ {id,name,weight,reps,sets,secs,time}, ... ] }
 *  ※1キー9KB/全体500KBの制限があるため月単位で分割（通常利用なら数年分保存可能）
 */

const PROP_NAME = 'BL_NAME';
const PROP_EX = 'BL_EX';
const PREFIX_COND = 'BL_C_';
const PREFIX_TRAIN = 'BL_T_';

/**
 * Webアプリ表示
 */
function doGet() {
  return HtmlService.createHtmlOutputFromFile('index')
    .setTitle('BODY LOG')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1, maximum-scale=1');
}

/**
 * ============================================
 * ストレージヘルパー
 * ============================================
 */

function props_() {
  return PropertiesService.getUserProperties();
}

function readJson_(key, fallback) {
  const raw = props_().getProperty(key);
  if (!raw) return fallback;
  try { return JSON.parse(raw); } catch (e) { return fallback; }
}

function writeJson_(key, obj) {
  props_().setProperty(key, JSON.stringify(obj));
}

/** 'yyyy-MM-dd' → 月キー */
function monthKey_(prefix, dateStr) {
  return prefix + dateStr.slice(0, 7);
}

/** 現在時刻 'HH:mm' */
function nowHM_() {
  return Utilities.formatDate(new Date(), 'Asia/Tokyo', 'HH:mm');
}

/** 入力値を保存用に整形（trimして空は''。数値も文字もそのまま保存） */
function cell_(v) {
  return String(v === null || v === undefined ? '' : v).trim();
}

/** 保存値を返却用に変換（空はnull） */
function cellOut_(v) {
  return (v === '' || v === null || v === undefined) ? null : v;
}

/**
 * ============================================
 * 会員登録・プロフィール
 * ============================================
 */

function getProfile() {
  const name = props_().getProperty(PROP_NAME);
  return {
    registered: !!name,
    name: name || '',
    email: Session.getActiveUser().getEmail() || ''
  };
}

/**
 * 初回登録: 名前(必須)を保存するだけ。ドライブもシートも作らない
 */
function registerUser(name) {
  const n = String(name || '').trim();
  if (!n) return { success: false, message: '名前を入力してください' };
  if (n.length > 30) return { success: false, message: '名前は30文字以内にしてください' };

  props_().setProperty(PROP_NAME, n);
  return { success: true, name: n, message: 'ようこそ、' + n + 'さん！' };
}

/**
 * ============================================
 * コンディション記録
 * ============================================
 */

function saveCondition(data) {
  const key = monthKey_(PREFIX_COND, data.date);
  const month = readJson_(key, {});
  month[data.date] = {
    weight: cell_(data.weight),
    sleep: cell_(data.sleep),
    fatigue: cell_(data.fatigue),
    score: cell_(data.score),
    memo: String(data.memo || ''),
    time: nowHM_()
  };
  writeJson_(key, month);
  return { success: true, message: data.date + ' のコンディションを保存しました' };
}

function getConditionByDate(dateStr) {
  const month = readJson_(monthKey_(PREFIX_COND, dateStr), {});
  const c = month[dateStr];
  if (!c) return null;
  return {
    date: dateStr,
    weight: c.weight,
    sleep: c.sleep,
    fatigue: c.fatigue,
    score: c.score,
    memo: c.memo
  };
}

/**
 * ============================================
 * トレーニング記録
 * ============================================
 */

function saveTraining(data) {
  if (!data.exercises || data.exercises.length === 0) {
    return { success: false, message: '種目が入力されていません' };
  }

  const key = monthKey_(PREFIX_TRAIN, data.date);
  const month = readJson_(key, {});
  const list = month[data.date] || [];
  const time = nowHM_();
  let seq = Date.now();

  data.exercises.forEach(function(ex) {
    list.push({
      id: seq++,
      name: String(ex.name).trim(),
      weight: cell_(ex.weight),
      reps: cell_(ex.reps),
      sets: cell_(ex.sets),
      secs: cell_(ex.secs),
      time: time
    });
  });
  month[data.date] = list;
  writeJson_(key, month);

  return {
    success: true,
    message: data.date + ' のトレーニング ' + data.exercises.length + '種目を保存しました',
    trainings: getTrainingByDate(data.date)
  };
}

function getTrainingByDate(dateStr) {
  const month = readJson_(monthKey_(PREFIX_TRAIN, dateStr), {});
  const list = month[dateStr] || [];
  return list.map(function(r) {
    return {
      row: r.id,   // UI互換のためidを"row"として返す
      date: dateStr,
      name: r.name,
      weight: cellOut_(r.weight),
      reps: cellOut_(r.reps),
      sets: cellOut_(r.sets),
      secs: cellOut_(r.secs),
      time: r.time || ''
    };
  });
}

function updateTrainingRow(payload) {
  if (!String(payload.name || '').trim()) {
    return { success: false, message: '種目を選択してください' };
  }
  const key = monthKey_(PREFIX_TRAIN, payload.date);
  const month = readJson_(key, {});
  const list = month[payload.date] || [];
  for (let i = 0; i < list.length; i++) {
    if (list[i].id === payload.row) {
      list[i].name = String(payload.name).trim();
      list[i].weight = cell_(payload.weight);
      list[i].reps = cell_(payload.reps);
      list[i].sets = cell_(payload.sets);
      list[i].secs = cell_(payload.secs);
      writeJson_(key, month);
      return { success: true, message: '記録を更新しました', trainings: getTrainingByDate(payload.date) };
    }
  }
  return { success: false, message: 'データが更新されています。画面を再読み込みしてください' };
}

function deleteTrainingRow(payload) {
  const key = monthKey_(PREFIX_TRAIN, payload.date);
  const month = readJson_(key, {});
  const list = month[payload.date] || [];
  const next = list.filter(function(r) { return r.id !== payload.row; });
  if (next.length === list.length) {
    return { success: false, message: 'データが更新されています。画面を再読み込みしてください' };
  }
  if (next.length === 0) {
    delete month[payload.date];
  } else {
    month[payload.date] = next;
  }
  writeJson_(key, month);
  return { success: true, message: '記録を削除しました', trainings: getTrainingByDate(payload.date) };
}

/**
 * ============================================
 * 種目マスタ（名前のみ）
 * ============================================
 */

function getExerciseNames() {
  return readJson_(PROP_EX, []);
}

function addExerciseName(name) {
  const n = String(name || '').trim();
  if (!n) return { success: false, message: '種目名が空です' };
  const names = readJson_(PROP_EX, []);
  if (names.indexOf(n) >= 0) {
    return { success: false, message: '「' + n + '」はすでに登録されています' };
  }
  names.push(n);
  writeJson_(PROP_EX, names);
  return { success: true, message: '「' + n + '」を登録しました' };
}

function deleteExerciseName(name) {
  const n = String(name || '').trim();
  const names = readJson_(PROP_EX, []);
  const next = names.filter(function(x) { return x !== n; });
  if (next.length === names.length) {
    return { success: false, message: '対象が見つかりません' };
  }
  writeJson_(PROP_EX, next);
  return { success: true, message: '「' + n + '」を削除しました' };
}

/**
 * ============================================
 * まとめ
 * ============================================
 */

function getSummary() {
  const all = props_().getProperties();

  // コンディション: 全月をマージして新しい順
  let conditions = [];
  Object.keys(all).forEach(function(key) {
    if (key.indexOf(PREFIX_COND) !== 0) return;
    let month;
    try { month = JSON.parse(all[key]); } catch (e) { return; }
    Object.keys(month).forEach(function(date) {
      const c = month[date];
      conditions.push({
        date: date,
        dateObj: new Date(date + 'T00:00:00').getTime(),
        weight: numOrNull_(c.weight),
        sleep: numOrNull_(c.sleep),
        fatigue: numOrNull_(c.fatigue),
        score: numOrNull_(c.score),
        memo: c.memo || '',
        time: c.time || ''
      });
    });
  });
  conditions.sort(function(a, b) { return b.dateObj - a.dateObj; });

  // トレーニング: 全月をマージして日付ごとにグループ化
  const trainByDate = {};
  Object.keys(all).forEach(function(key) {
    if (key.indexOf(PREFIX_TRAIN) !== 0) return;
    let month;
    try { month = JSON.parse(all[key]); } catch (e) { return; }
    Object.keys(month).forEach(function(date) {
      trainByDate[date] = month[date].map(function(r) {
        return {
          row: r.id,
          date: date,
          name: r.name,
          weight: cellOut_(r.weight),
          reps: cellOut_(r.reps),
          sets: cellOut_(r.sets),
          secs: cellOut_(r.secs),
          time: r.time || ''
        };
      });
    });
  });
  const trainDates = Object.keys(trainByDate).sort().reverse();
  const recentTrainings = trainDates.slice(0, 60).map(function(date) {
    return { date: date, exercises: trainByDate[date] };
  });

  return {
    conditions: conditions.slice(0, 60),
    recentTrainings: recentTrainings
  };
}

function numOrNull_(v) {
  if (v === '' || v === null || v === undefined) return null;
  const n = Number(v);
  return isNaN(n) ? null : n;
}

/**
 * ============================================
 * 高速化: 初期データ一括取得
 * ============================================
 */

function getInitData(dateStr) {
  const profile = getProfile();
  if (!profile.registered) {
    return { profile: profile };
  }
  return {
    profile: profile,
    exerciseNames: getExerciseNames(),
    condition: getConditionByDate(dateStr),
    trainings: getTrainingByDate(dateStr)
  };
}
