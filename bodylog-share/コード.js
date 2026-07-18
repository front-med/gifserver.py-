/**
 * ============================================
 * BODY LOG Share（共有版・マルチユーザー）
 * ============================================
 * 仕組み:
 *  - Web Appを「アクセスしているユーザーとして実行」でデプロイ
 *    → Googleアカウントでのログインが必須（匿名アクセス不可）
 *  - 初回アクセス時に名前を登録（必須）。会員登録の位置づけ
 *  - データは各ユーザー自身のGoogleドライブに自動作成される
 *    スプレッドシート「BODY LOG - <名前>」に保存される
 *    → 他人のデータは構造上見えない（完全に個人別）
 *  - 共有機能: コンディション記録 / トレーニング記録 / まとめ のみ
 *    （フォーム素材・CLIP→GIF連携・体重自動受信・LINEレポートは本家のみ）
 */

const SHEET_CONDITION = 'コンディション';
const SHEET_TRAINING = 'トレーニング';
const SHEET_EXERCISE = '種目マスタ';
const PROP_SS_ID = 'BL_SS_ID';
const PROP_NAME = 'BL_NAME';

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
 * 会員登録・プロフィール
 * ============================================
 */

/**
 * ログイン中ユーザーのプロフィールを取得
 */
function getProfile() {
  const props = PropertiesService.getUserProperties();
  const name = props.getProperty(PROP_NAME);
  const ssId = props.getProperty(PROP_SS_ID);
  return {
    registered: !!(name && ssId),
    name: name || '',
    email: Session.getActiveUser().getEmail() || ''
  };
}

/**
 * 初回登録: 名前(必須)を保存し、本人のドライブに記録用スプレッドシートを作成
 */
function registerUser(name) {
  const n = String(name || '').trim();
  if (!n) return { success: false, message: '名前を入力してください' };
  if (n.length > 30) return { success: false, message: '名前は30文字以内にしてください' };

  const props = PropertiesService.getUserProperties();
  let ssId = props.getProperty(PROP_SS_ID);
  if (!ssId) {
    const ss = SpreadsheetApp.create('BODY LOG - ' + n);
    setupSheets_(ss);
    ssId = ss.getId();
    props.setProperty(PROP_SS_ID, ssId);
  }
  props.setProperty(PROP_NAME, n);
  return { success: true, name: n, message: 'ようこそ、' + n + 'さん！' };
}

/**
 * 登録済みユーザーのスプレッドシートを開く
 */
function userSs_() {
  const ssId = PropertiesService.getUserProperties().getProperty(PROP_SS_ID);
  if (!ssId) throw new Error('未登録です。ページを再読み込みして名前を登録してください');
  return SpreadsheetApp.openById(ssId);
}

/**
 * シート初期構築（ユーザーごとのスプレッドシートに作成）
 */
function setupSheets_(ss) {
  const condSheet = ss.insertSheet(SHEET_CONDITION);
  condSheet.getRange(1, 1, 1, 7).setValues([[
    '日付', '体重(kg)', '睡眠時間(h)', '疲労度(1-5)', '体調スコア(1-5)', 'メモ', '記録時刻'
  ]]);
  condSheet.getRange(1, 1, 1, 7)
    .setBackground('#111111').setFontColor('#ffffff').setFontWeight('bold');
  condSheet.setFrozenRows(1);
  condSheet.getRange('A:A').setNumberFormat('yyyy/mm/dd');
  condSheet.getRange('G:G').setNumberFormat('yyyy/mm/dd hh:mm');

  const trainSheet = ss.insertSheet(SHEET_TRAINING);
  trainSheet.getRange(1, 1, 1, 6).setValues([[
    '日付', '種目', '重量(kg)', '回数', 'セット数', '記録時刻'
  ]]);
  trainSheet.getRange(1, 1, 1, 6)
    .setBackground('#111111').setFontColor('#ffffff').setFontWeight('bold');
  trainSheet.setFrozenRows(1);
  trainSheet.getRange('A:A').setNumberFormat('yyyy/mm/dd');
  trainSheet.getRange('F:F').setNumberFormat('yyyy/mm/dd hh:mm');

  const exSheet = ss.insertSheet(SHEET_EXERCISE);
  exSheet.getRange(1, 1, 1, 2).setValues([['種目名', '登録日']]);
  exSheet.getRange(1, 1, 1, 2)
    .setBackground('#111111').setFontColor('#ffffff').setFontWeight('bold');
  exSheet.setFrozenRows(1);
  exSheet.setColumnWidth(1, 180);

  // デフォルトの「シート1」を削除
  const defaultSheet = ss.getSheets()[0];
  if (ss.getSheets().length > 1 && defaultSheet.getName() !== SHEET_CONDITION) {
    ss.deleteSheet(defaultSheet);
  }
}

/**
 * ============================================
 * 共通ヘルパー
 * ============================================
 */

function num_(v) {
  if (v === '' || v === null || v === undefined) return null;
  const n = Number(v);
  return isNaN(n) ? null : n;
}

function parseDate_(dateStr) {
  const parts = dateStr.split('-');
  return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
}

function formatDate_(date) {
  return Utilities.formatDate(date, 'Asia/Tokyo', 'yyyy-MM-dd');
}

/**
 * ============================================
 * コンディション記録
 * ============================================
 */

function saveCondition(data) {
  const sheet = userSs_().getSheetByName(SHEET_CONDITION);
  const targetDate = parseDate_(data.date);

  const lastRow = sheet.getLastRow();
  let rowToWrite = lastRow + 1;

  if (lastRow >= 2) {
    const dates = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
    for (let i = 0; i < dates.length; i++) {
      if (dates[i][0] instanceof Date && formatDate_(dates[i][0]) === data.date) {
        rowToWrite = i + 2;
        break;
      }
    }
  }

  sheet.getRange(rowToWrite, 1, 1, 7).setValues([[
    targetDate,
    data.weight !== '' ? Number(data.weight) : '',
    data.sleep !== '' ? Number(data.sleep) : '',
    data.fatigue !== '' ? Number(data.fatigue) : '',
    data.score !== '' ? Number(data.score) : '',
    data.memo || '',
    new Date()
  ]]);

  return { success: true, message: data.date + ' のコンディションを保存しました' };
}

function getConditionByDate(dateStr) {
  const sheet = userSs_().getSheetByName(SHEET_CONDITION);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return null;

  const values = sheet.getRange(2, 1, lastRow - 1, 6).getValues();
  for (let i = 0; i < values.length; i++) {
    if (values[i][0] instanceof Date && formatDate_(values[i][0]) === dateStr) {
      return {
        date: dateStr,
        weight: values[i][1],
        sleep: values[i][2],
        fatigue: values[i][3],
        score: values[i][4],
        memo: values[i][5]
      };
    }
  }
  return null;
}

/**
 * ============================================
 * トレーニング記録
 * ============================================
 */

function saveTraining(data) {
  const sheet = userSs_().getSheetByName(SHEET_TRAINING);
  const targetDate = parseDate_(data.date);

  const now = new Date();
  const rows = data.exercises.map(function(ex) {
    return [
      targetDate,
      ex.name,
      ex.weight !== '' ? Number(ex.weight) : '',
      ex.reps !== '' ? Number(ex.reps) : '',
      ex.sets !== '' ? Number(ex.sets) : '',
      now
    ];
  });

  if (rows.length === 0) {
    return { success: false, message: '種目が入力されていません' };
  }

  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, 6).setValues(rows);

  return {
    success: true,
    message: data.date + ' のトレーニング ' + rows.length + '種目を保存しました',
    trainings: getTrainingByDate(data.date)
  };
}

function getTrainingByDate(dateStr) {
  const sheet = userSs_().getSheetByName(SHEET_TRAINING);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];

  const values = sheet.getRange(2, 1, lastRow - 1, 6).getValues();
  const result = [];
  for (let i = 0; i < values.length; i++) {
    const r = values[i];
    if (r[0] instanceof Date && formatDate_(r[0]) === dateStr) {
      result.push({
        row: i + 2,
        date: dateStr,
        name: r[1],
        weight: num_(r[2]),
        reps: num_(r[3]),
        sets: num_(r[4]),
        time: (r[5] instanceof Date) ? Utilities.formatDate(r[5], 'Asia/Tokyo', 'HH:mm') : ''
      });
    }
  }
  return result;
}

function verifyTrainRow_(sheet, row, dateStr) {
  const v = sheet.getRange(row, 1).getValue();
  return (v instanceof Date) && formatDate_(v) === dateStr;
}

function updateTrainingRow(payload) {
  try {
    const sheet = userSs_().getSheetByName(SHEET_TRAINING);

    if (!verifyTrainRow_(sheet, payload.row, payload.date)) {
      return { success: false, message: 'データが更新されています。画面を再読み込みしてください' };
    }
    if (!String(payload.name || '').trim()) {
      return { success: false, message: '種目を選択してください' };
    }

    sheet.getRange(payload.row, 2, 1, 4).setValues([[
      String(payload.name).trim(),
      payload.weight !== '' && payload.weight !== null ? Number(payload.weight) : '',
      payload.reps !== '' && payload.reps !== null ? Number(payload.reps) : '',
      payload.sets !== '' && payload.sets !== null ? Number(payload.sets) : ''
    ]]);

    return { success: true, message: '記録を更新しました', trainings: getTrainingByDate(payload.date) };
  } catch (err) {
    return { success: false, message: 'エラー: ' + err.message };
  }
}

function deleteTrainingRow(payload) {
  try {
    const sheet = userSs_().getSheetByName(SHEET_TRAINING);

    if (!verifyTrainRow_(sheet, payload.row, payload.date)) {
      return { success: false, message: 'データが更新されています。画面を再読み込みしてください' };
    }

    sheet.deleteRow(payload.row);
    return { success: true, message: '記録を削除しました', trainings: getTrainingByDate(payload.date) };
  } catch (err) {
    return { success: false, message: 'エラー: ' + err.message };
  }
}

/**
 * ============================================
 * 種目マスタ（名前のみ・素材機能なし）
 * ============================================
 */

function getExerciseNames() {
  const sheet = userSs_().getSheetByName(SHEET_EXERCISE);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];

  const values = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
  const names = [];
  values.forEach(function(r) {
    const name = String(r[0]).trim();
    if (name) names.push(name);
  });
  return names;
}

function addExerciseName(name) {
  const n = String(name || '').trim();
  if (!n) return { success: false, message: '種目名が空です' };

  const sheet = userSs_().getSheetByName(SHEET_EXERCISE);
  const lastRow = sheet.getLastRow();

  if (lastRow >= 2) {
    const names = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
    for (let i = 0; i < names.length; i++) {
      if (String(names[i][0]).trim() === n) {
        return { success: false, message: '「' + n + '」はすでに登録されています' };
      }
    }
  }

  sheet.getRange(lastRow + 1, 1, 1, 2).setValues([[n, new Date()]]);
  return { success: true, message: '「' + n + '」を登録しました' };
}

function deleteExerciseName(name) {
  const sheet = userSs_().getSheetByName(SHEET_EXERCISE);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { success: false, message: '対象がありません' };

  const values = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
  for (let i = 0; i < values.length; i++) {
    if (String(values[i][0]).trim() === String(name).trim()) {
      sheet.deleteRow(i + 2);
      return { success: true, message: '「' + name + '」を削除しました' };
    }
  }
  return { success: false, message: '対象が見つかりません' };
}

/**
 * ============================================
 * まとめ
 * ============================================
 */

function getSummary() {
  const ss = userSs_();
  const condSheet = ss.getSheetByName(SHEET_CONDITION);
  const trainSheet = ss.getSheetByName(SHEET_TRAINING);

  let conditions = [];
  const condLast = condSheet.getLastRow();
  if (condLast >= 2) {
    const values = condSheet.getRange(2, 1, condLast - 1, 7).getValues();
    conditions = values
      .filter(function(r) { return r[0] instanceof Date; })
      .map(function(r) {
        return {
          date: formatDate_(r[0]),
          dateObj: r[0].getTime(),
          weight: num_(r[1]),
          sleep: num_(r[2]),
          fatigue: num_(r[3]),
          score: num_(r[4]),
          memo: r[5] || '',
          time: (r[6] instanceof Date) ? Utilities.formatDate(r[6], 'Asia/Tokyo', 'HH:mm') : ''
        };
      })
      .sort(function(a, b) { return b.dateObj - a.dateObj; });
  }

  let trainings = [];
  const trainLast = trainSheet.getLastRow();
  if (trainLast >= 2) {
    const values = trainSheet.getRange(2, 1, trainLast - 1, 6).getValues();
    trainings = values
      .map(function(r, i) {
        if (!(r[0] instanceof Date)) return null;
        return {
          row: i + 2,
          date: formatDate_(r[0]),
          dateObj: r[0].getTime(),
          name: r[1],
          weight: num_(r[2]),
          reps: num_(r[3]),
          sets: num_(r[4]),
          time: (r[5] instanceof Date) ? Utilities.formatDate(r[5], 'Asia/Tokyo', 'HH:mm') : ''
        };
      })
      .filter(function(t) { return t !== null; })
      .sort(function(a, b) { return b.dateObj - a.dateObj; });
  }

  const trainByDate = {};
  const trainDateOrder = [];
  trainings.forEach(function(t) {
    if (!trainByDate[t.date]) {
      trainByDate[t.date] = [];
      trainDateOrder.push(t.date);
    }
    trainByDate[t.date].push(t);
  });

  const recentTrainings = trainDateOrder.slice(0, 60).map(function(date) {
    return { date: date, exercises: trainByDate[date] };
  });

  return {
    conditions: conditions.slice(0, 60),
    trainingRows: trainings.slice(0, 100),
    recentTrainings: recentTrainings
  };
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
