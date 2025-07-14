```markdown
## Problem Statement: Hashing Secrets

In a distant land, a group of wizards is trying to secure their magical spells using a unique hashing mechanism. Each spell is represented as a string of lowercase letters. The wizards decided to use a hash function that maps each string to a unique integer based on the characters it contains.

The hash function is defined as follows:

1. For each character in the string, compute its position in the alphabet (a=1, b=2, ..., z=26).
2. Compute the hash of the string as the sum of these positions, multiplied by the length of the string.

For example, the hash of the string "abc" is computed as:
- a → 1
- b → 2
- c → 3
- hash("abc") = (1 + 2 + 3) * 3 = 18

The wizards want to check if there are any pairs of spells that produce the same hash value. Your task is to help them by writing a function that determines the number of unique hash values produced by the spells and the number of pairs of spells that have the same hash value.

### Input Format

- The first line of input contains an integer `n` (1 ≤ n ≤ 10^5) - the number of spells.
- The next `n` lines each contain a string `s_i` (1 ≤ |s_i| ≤ 100) - the spell represented as a string of lowercase letters.

### Output Format

- The first line should output the number of unique hash values produced by the spells.
- The second line should output the number of pairs of spells that have the same hash value.

### Constraints

- Each spell string will only consist of lowercase English letters.
- The input will not include any empty strings.
  
### Example

#### Input
```
5
abc
bca
ac
xyz
zxy
```

#### Output
```
3
2
```

### Explanation

- The unique hash values for the spells are:
  - "abc" and "bca" both produce a hash of 18.
  - "ac" produces a hash of 12.
  - "xyz" and "zxy" both produce a hash of 72.
  
Therefore, the unique hash values are 3 (18, 12, and 72), and there are 2 pairs of spells that share the same hash (("abc", "bca") and ("xyz", "zxy")).

### Note

- Make sure to handle cases where multiple spells can produce the same hash efficiently.
- The solution should ideally run in O(n) or O(n log n) time complexity.
```
