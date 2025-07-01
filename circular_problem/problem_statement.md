# Magical Circle Segmentation with Modulo

A powerful wizard has arranged N enchanted runes in a circle. Each rune carries an integer power (which may be positive, negative, or zero). The wizard wants to **cut** the circle at some rune (choosing any starting point) and then **partition** the entire circular sequence into one or more non-empty contiguous segments. For each segment, he computes the sum of powers of the runes in that segment, and then he takes the product of all these segment‐sum values to produce a final magical potency.

Because the potency can be astronomically large, the wizard only cares about its value **modulo** 1 000 000 007. Help him determine the **maximum** possible potency (taken modulo 1 000 000 007) over all choices of starting position and ways to break the circle into segments.

## Input Format

The first line contains an integer  
```
N
```  
—the number of runes in the circle.

The second line contains N space-separated integers  
```
A_1 A_2 … A_N
```  
where `A_i` is the power value of the _i_-th rune in circular order.

## Output Format

Print a single integer: the maximum potency the wizard can achieve, **modulo** 1 000 000 007.

## Constraints

- 1 ≤ N ≤ 2000  
- –1000 ≤ A_i ≤ 1000  for all 1 ≤ i ≤ N  
- Time limit: O(N²) (or better) expected.  
- No external big‐integer libraries are needed; all outputs are taken mod 1 000 000 007.

## Example

#### Example 1
Input:
```
4
1 -2 3 4
```
Output:
```
8
```
Explanation:  
Rotate to start at 4, partition into `[4]` and `[1,-2,3]`.  
Segment sums: 4 and 2 → product = 8 mod 1e9+7.

#### Example 2
Input:
```
3
-1 -2 -3
```
Output:
```
9
```
Explanation:  
One optimal cut yields segments `[-1,-2]` and `[-3]`.  
Sums = –3 and –3; product = 9 mod 1e9+7.

#### Example 3
Input:
```
5
2 2 2 2 2
```
Output:
```
32
```
Explanation:  
Best is five segments `[2]` each: product = 2⁵ = 32 mod 1e9+7.