import { useEffect, useState } from 'react';
import { View, Text, FlatList } from 'react-native';
import { useRouter } from 'expo-router';
import { Button } from 'react-native';

const API_URL = process.env.EXPO_PUBLIC_API_URL;

export default function DashboardScreen() {
  const router = useRouter();
  const [transactions, setTransactions] = useState([]);

  useEffect(() => {
    fetch(`${API_URL}/transactions`)
      .then(res => res.json())
      .then(setTransactions)
      .catch(err => console.error(err));
  }, []);

  return (
    <View style={{ padding: 20 }}>
      <Text style={{ fontSize: 20, fontWeight: 'bold', marginBottom: 10 }}>Recent Transactions</Text>
      <Button title="Add Transaction" onPress={() => {router.push('/add-transaction' as any)}} />
      <FlatList
        data={transactions}
        keyExtractor={item => item.id}
        renderItem={({ item }) => (
          <View style={{ paddingVertical: 8, borderBottomWidth: 1, borderColor: '#eee' }}>
            <Text>{item.description_raw}</Text>
            <Text style={{ color: item.amount < 0 ? 'red' : 'green' }}>{item.amount} {item.currency}</Text>
          </View>
        )}
      />
    </View>
  );
}