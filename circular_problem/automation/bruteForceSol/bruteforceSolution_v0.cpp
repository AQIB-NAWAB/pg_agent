#include <bits/stdc++.h>
using namespace std;
using int64 = long long;
const int64 MOD = 1000000007;
int main(){
    ios::sync_with_stdio(false);
    cin.tie(NULL);

    int N;
    cin >> N;
    vector<int64> A(N);
    for(int i = 0; i < N; i++) cin >> A[i];

    __int128 best = LLONG_MIN;
    for(int st = 0; st < N; st++){
        vector<int64> B(N);
        for(int i = 0; i < N; i++){
            B[i] = A[(st + i) % N];
        }
        vector<__int128> P(N+1, 0);
        for(int i = 0; i < N; i++) P[i+1] = P[i] + B[i];
        vector<__int128> dp_max(N), dp_min(N);
        for(int i = 0; i < N; i++){
            dp_max[i] = LLONG_MIN;
            dp_min[i] = LLONG_MAX;
            for(int j = 0; j <= i; j++){
                __int128 s = P[i+1] - P[j];
                if(j == 0){
                    dp_max[i] = max(dp_max[i], s);
                    dp_min[i] = min(dp_min[i], s);
                } else {
                    __int128 a = dp_max[j-1] * s;
                    __int128 b = dp_min[j-1] * s;
                    dp_max[i] = max(dp_max[i], max(a,b));
                    dp_min[i] = min(dp_min[i], min(a,b));
                }
            }
        }
        best = max(best, dp_max[N-1]);
    }

    int64 ans = (int64)(best % MOD);
    if(ans < 0) ans += MOD;
    cout << ans << "\n";
    return 0;
}