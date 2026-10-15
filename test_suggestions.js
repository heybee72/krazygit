// Run: node test_suggestions.js  (checks the conflict suggestions in krazygit.html)
const fs = require('fs'), src = fs.readFileSync(__dirname + '/krazygit.html', 'utf8')
const plural = (n, w, m = w + 's') => `${n} ${n === 1 ? w : m}`
eval(src.slice(src.indexOf('const keyLines = '), src.indexOf('const HOW_TO_CHOOSE = ')).replace(/^const (\w+) =/gm, 'var $1 =').replace(/^function (\w+)/gm, 'var $1 = function'))
const assert = require('assert')
const M = 'Yours', T = 'Incoming', u = n => `use App\\Models\\${n};\n`
// 1. yours has everything incoming has, plus more (no usable original)
let x = { ours: ['OrderApproval', 'OrderApprovalAction', 'OrderApprovalAssignment', 'OrderChecklist', 'OrderHistory', 'OrderTask'].map(u).join(''),
          theirs: ['OrderHistory', 'OrderTask', 'OrderChecklist'].map(u).join('') }
let a = advise(x, M, T)
assert.equal(a.pick, 'ours'); assert.equal(a.onlyO.length, 3); assert.equal(a.onlyT.length, 0)
console.log('superset ->', a.pick, '|', a.why)
// 2. each side added a different import (original known) -> combine, no duplicates
x = { base: u('A'), ours: u('A') + u('B'), theirs: u('A') + u('C'), hasBase: true }
a = advise(x, M, T); assert.equal(a.pick, 'combine')
assert.equal(combine(x, '\n'), u('A') + u('B') + u('C'))
// 3. both changed the same line differently -> your call, never automatic
x = { base: 'timeout = 10\n', ours: 'timeout = 20\n', theirs: 'timeout = 30\n', hasBase: true }
a = advise(x, M, T); assert.equal(a.pick, null); console.log('same line ->', a.why)
// 4. incoming deleted a line that yours still has: "keep yours" would bring it back, so don't suggest it
x = { base: u('A') + u('Old'), ours: u('A') + u('Old') + u('New'), theirs: u('A'), hasBase: true }
a = advise(x, M, T); assert.notEqual(a.pick, 'ours'); assert.equal(a.pick, 'combine')
assert.equal(combine(x, '\n'), u('A') + u('New'))   // Old stays deleted, New is kept
// 5. same lines, different order -> either is fine
x = { ours: u('A') + u('B'), theirs: u('B') + u('A') }
assert.equal(advise(x, M, T).pick, 'ours')
// 6. no original and both sides have their own lines -> your call (combine stays available)
x = { ours: u('A') + u('B'), theirs: u('A') + u('C') }
assert.equal(advise(x, M, T).pick, null)
assert.equal(combine(x, '\n'), u('A') + u('B') + u('C'))
// 7. Windows line endings survive combining
x = { base: 'a\r\n', ours: 'a\r\nb\r\n', theirs: 'a\r\nc\r\n', hasBase: true }
assert.equal(combine(x, '\r\n'), 'a\r\nb\r\nc\r\n')
console.log('all suggestion checks pass')
