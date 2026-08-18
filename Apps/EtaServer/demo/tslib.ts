// tslib.ts - TypeScript 业务库示例
//
// 由 Node 22.18+ 内置类型剥离支持，模板里直接 require('./tslib.ts')，
// 无需 tsc / ts-node / tsx。注意仅支持可擦除语法：类型注解、interface、
// type、泛型可用；enum、namespace、参数属性不可用。

export interface User {
  name: string
  age: number
}

export function formatUser (u: User): string {
  return u.name + ' (age ' + String(u.age) + ')'
}

export function sum <T extends number> (list: T[]): number {
  let total: number = 0
  for (const n of list) total += n
  return total
}
