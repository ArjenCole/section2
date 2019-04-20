using SoftCircuits;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;


namespace section2
{
    public static class mscExp
    {
        public static double Doub(string pExp)
        {            
            // Evaluate the current expression
            try
            {
                Eval eval = new Eval();
                eval.ProcessSymbol += ProcessSymbol;
                eval.ProcessFunction += ProcessFunction;
                return eval.Execute(pExp);
            }
            catch
            {
                return 0.0;
            }
        }
        public static string Str(string pExp)
        {
            return Doub(pExp).ToString();
        }

        // Implement expression symbols
        private static void ProcessSymbol(object sender, SymbolEventArgs e)
        {
            //if (String.Compare(e.Name, "pi", true) == 0)
            //{
            //    e.Result = Math.PI;
            //}
            //// Unknown symbol name
            //else e.Status = SymbolStatus.UndefinedSymbol;
        }

        // Implement expression functions
        private static void ProcessFunction(object sender, FunctionEventArgs e)
        {
            if (String.Compare(e.Name, "abs", true) == 0)
            {
                if (e.Parameters.Count == 1)
                    e.Result = Math.Abs(e.Parameters[0]);
                else
                    e.Status = FunctionStatus.WrongParameterCount;
            }
            else if (String.Compare(e.Name, "pi", true) == 0)
            {
                if (e.Parameters.Count == 0)
                    e.Result = Math.PI;
                else
                    e.Status = FunctionStatus.WrongParameterCount;
            }
            else if (String.Compare(e.Name, "power", true) == 0)
            {
                if (e.Parameters.Count == 2)
                    e.Result = Math.Pow(e.Parameters[0], e.Parameters[1]);
                else
                    e.Status = FunctionStatus.WrongParameterCount;
            }
            else if (String.Compare(e.Name, "round", true) == 0)
            {
                if (e.Parameters.Count == 2)
                    e.Result = Math.Round(e.Parameters[0], Convert.ToInt16(e.Parameters[1]));
                else if (e.Parameters.Count == 1)
                    e.Result = Math.Round(e.Parameters[0], 0);
                else
                    e.Status = FunctionStatus.WrongParameterCount;
            }
            else if (String.Compare(e.Name, "roundup", true) == 0)
            {
                if (e.Parameters.Count == 2)
                {
                    double tPower = Math.Pow(10, Convert.ToInt16(e.Parameters[1]));
                    e.Result = Math.Ceiling(e.Parameters[0] * tPower) / tPower;
                }   
                else if (e.Parameters.Count == 1)
                {
                    e.Result = Math.Ceiling(e.Parameters[0]);
                }
                else
                {
                    e.Status = FunctionStatus.WrongParameterCount;
                }   
            }
            else if (String.Compare(e.Name, "sqrt", true) == 0)
            {
                if (e.Parameters.Count == 1)
                    e.Result = Math.Sqrt(e.Parameters[0]);
                else
                    e.Status = FunctionStatus.WrongParameterCount;
            }
            // Unknown function name
            else e.Status = FunctionStatus.UndefinedFunction;
        }

    }
}
