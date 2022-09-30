const CHAR_FREQ = require('../assets/materials/characters/char_freq.json');

let CharFreq = Object.keys(CHAR_FREQ).map((key) => ({
  character: key,
  frequency: CHAR_FREQ[key],
}));

const backvertStudentLevel = (studentLevel) => {
  return 1 / Math.log(studentLevel) ** 10;
};
const getStudentSet = (studentFrequency) => {
  return CharFreq.filter((n) => n.frequency <= studentFrequency);
};

const makeIndicator = (studentFrequency, lowestFrequency) => {
  return (
    Math.random() * (studentFrequency - lowestFrequency) + lowestFrequency
  );
};

const characterPicker = (lvl) => {
  let studentFrequency = backvertStudentLevel(lvl);
  console.log('studentFrequency: ' + studentFrequency);
  let studentSetFull = getStudentSet(studentFrequency);

  let studentSet =
    studentSetFull.length <= 500
      ? studentSetFull
      : studentSetFull.splice(-1, 500);

  console.log(studentSetFull);

  let lowestFrequency = studentSet.reduce((prev, curr) =>
    prev.frequency < curr.frequency ? prev : curr
  ).frequency;

  console.log('studentSet: ' + studentSet);
  let indicator = makeIndicator(studentFrequency, lowestFrequency);
  console.log('indicator: ' + indicator);

  return studentSet.reduce((acc, obj) =>
    Math.abs(indicator - obj.frequency) <
    Math.abs(indicator - acc.frequency)
      ? obj
      : acc
  ).character;
};

characterPicker(1);
