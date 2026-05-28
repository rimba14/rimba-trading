import { cellAtIndex, CellWidth, type Screen } from './screen.js'

export function buildSearchableRowText(screen: Screen, rowOff: number): {
  text: string
  colOf: number[]
  codeUnitToCell: number[]
} {
  let text = ''
  const colOf: number[] = []
  const codeUnitToCell: number[] = []
  const w = screen.width
  const noSelect = screen.noSelect

  for (let col = 0; col < w; col++) {
    const idx = rowOff + col
    const cell = cellAtIndex(screen, idx)

    if (cell.width === CellWidth.SpacerTail || cell.width === CellWidth.SpacerHead || noSelect[idx] === 1) {
      continue
    }

    const lc = cell.char.toLowerCase()
    const cellIdx = colOf.length

    for (let i = 0; i < lc.length; i++) {
      codeUnitToCell.push(cellIdx)
    }

    text += lc
    colOf.push(col)
  }

  return { text, colOf, codeUnitToCell }
}
