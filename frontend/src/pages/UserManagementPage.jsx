import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { getUsers, createUser, updateUser, deleteUser } from "../api/usersApi";

export function UserManagementPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [formData, setFormData] = useState({
    username: "",
    password: "",
    first_name: "",
    last_name: "",
    email: "",
    role: "data_entry",
    is_active: true,
    assigned_auditor_id: null,
  });

  const roles = [
    { value: "admin", label: "Admin" },
    { value: "data_entry", label: "Data Entry" },
    { value: "auditor", label: "Auditor" },
    { value: "reader", label: "Reader" },
  ];

  const [auditors, setAuditors] = useState([]);

  useEffect(() => {
    if (user?.role !== "admin") {
      navigate("/forbidden");
      return;
    }
    fetchUsers();
  }, [user, navigate]);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const response = await getUsers();
      setUsers(response.data.results || []);
      // Extract auditors for the dropdown
      const auditorList = (response.data.results || []).filter(
        (u) => u.role === "auditor"
      );
      setAuditors(auditorList);
      setError(null);
    } catch (err) {
      setError("Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData({
      ...formData,
      [name]: type === "checkbox" ? checked : value,
    });
  };

  const handleAuditorChange = (e) => {
    const value = e.target.value;
    setFormData({
      ...formData,
      assigned_auditor_id: value === "" ? null : parseInt(value, 10),
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const data = { ...formData };
      if (!data.password && isEditing) {
        delete data.password;
      }
      if (data.role !== "data_entry") {
        data.assigned_auditor_id = null;
      }

      if (isEditing) {
        await updateUser(editingUser.id, data);
      } else {
        await createUser(data);
      }
      resetForm();
      fetchUsers();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to save user");
    }
  };

  const handleEdit = (userToEdit) => {
    setIsEditing(true);
    setEditingUser(userToEdit);
    setFormData({
      username: userToEdit.username,
      password: "",
      first_name: userToEdit.first_name || "",
      last_name: userToEdit.last_name || "",
      email: userToEdit.email || "",
      role: userToEdit.role,
      is_active: userToEdit.is_active,
      assigned_auditor_id: userToEdit.assigned_auditor_id,
    });
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Are you sure you want to delete this user?")) {
      return;
    }
    try {
      await deleteUser(id);
      fetchUsers();
    } catch (err) {
      setError("Failed to delete user");
    }
  };

  const resetForm = () => {
    setIsEditing(false);
    setEditingUser(null);
    setFormData({
      username: "",
      password: "",
      first_name: "",
      last_name: "",
      email: "",
      role: "data_entry",
      is_active: true,
      assigned_auditor_id: null,
    });
    setError(null);
  };

  if (loading && users.length === 0) {
    return <div>Loading...</div>;
  }

  return (
    <div style={{ padding: "20px" }}>
      <h1>User Management</h1>

      {error && (
        <div
          style={{
            padding: "10px",
            marginBottom: "10px",
            backgroundColor: "#fee",
            color: "#c00",
          }}
        >
          {error}
        </div>
      )}

      <div style={{ marginBottom: "20px" }}>
        <h2>{isEditing ? "Edit User" : "Create User"}</h2>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: "10px" }}>
            <label>Username:</label>
            <input
              type="text"
              name="username"
              value={formData.username}
              onChange={handleInputChange}
              required
              style={{ marginLeft: "10px" }}
            />
          </div>

          <div style={{ marginBottom: "10px" }}>
            <label>Password:</label>
            <input
              type="password"
              name="password"
              value={formData.password}
              onChange={handleInputChange}
              placeholder={isEditing ? "Leave blank to keep unchanged" : ""}
              required={!isEditing}
              style={{ marginLeft: "10px" }}
            />
          </div>

          <div style={{ marginBottom: "10px" }}>
            <label>First Name:</label>
            <input
              type="text"
              name="first_name"
              value={formData.first_name}
              onChange={handleInputChange}
              style={{ marginLeft: "10px" }}
            />
          </div>

          <div style={{ marginBottom: "10px" }}>
            <label>Last Name:</label>
            <input
              type="text"
              name="last_name"
              value={formData.last_name}
              onChange={handleInputChange}
              style={{ marginLeft: "10px" }}
            />
          </div>

          <div style={{ marginBottom: "10px" }}>
            <label>Email:</label>
            <input
              type="email"
              name="email"
              value={formData.email}
              onChange={handleInputChange}
              style={{ marginLeft: "10px" }}
            />
          </div>

          <div style={{ marginBottom: "10px" }}>
            <label>Role:</label>
            <select
              name="role"
              value={formData.role}
              onChange={handleInputChange}
              style={{ marginLeft: "10px" }}
            >
              {roles.map((role) => (
                <option key={role.value} value={role.value}>
                  {role.label}
                </option>
              ))}
            </select>
          </div>

          {formData.role === "data_entry" && (
            <div style={{ marginBottom: "10px" }}>
              <label>Assigned Auditor:</label>
              <select
                value={formData.assigned_auditor_id || ""}
                onChange={handleAuditorChange}
                style={{ marginLeft: "10px" }}
              >
                <option value="">None</option>
                {auditors.map((auditor) => (
                  <option key={auditor.id} value={auditor.id}>
                    {auditor.username}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div style={{ marginBottom: "10px" }}>
            <label>
              <input
                type="checkbox"
                name="is_active"
                checked={formData.is_active}
                onChange={handleInputChange}
              />
              Active
            </label>
          </div>

          <div>
            <button type="submit" style={{ marginRight: "10px" }}>
              {isEditing ? "Update" : "Create"}
            </button>
            {isEditing && (
              <button type="button" onClick={resetForm}>
                Cancel
              </button>
            )}
          </div>
        </form>
      </div>

      <div>
        <h2>المستخدمون</h2>
        <table className="data-table" style={{ width: "100%" }}>
          <thead>
            <tr>
              <th>اسم المستخدم</th>
              <th>الاسم الكامل</th>
              <th>الدور</th>
              <th>المدقق المرتبط</th>
              <th>الإجراءات</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.username}</td>
                <td>
                  {u.first_name || u.last_name
                    ? `${u.first_name || ""} ${u.last_name || ""}`.trim()
                    : "—"}
                </td>
                <td>
                  <span
                    className={`role-badge role-${u.role}`}
                    style={{
                      display: "inline-block",
                      padding: "0.25rem 0.5rem",
                      borderRadius: "4px",
                      fontSize: "0.85rem",
                      fontWeight: 600,
                      background: u.role === "admin" ? "#fee2e2" : u.role === "auditor" ? "#dbeafe" : u.role === "data_entry" ? "#fef3c7" : "#f3f4f6",
                      color: u.role === "admin" ? "#991b1b" : u.role === "auditor" ? "#1e40af" : u.role === "data_entry" ? "#92400e" : "#374151",
                    }}
                  >
                    {u.role === "admin"
                      ? "مدير"
                      : u.role === "auditor"
                      ? "مدقق"
                      : u.role === "data_entry"
                      ? "مدخل بيانات"
                      : u.role === "reader"
                      ? "قارئ"
                      : u.role}
                  </span>
                </td>
                <td>
                  {u.assigned_auditor_id
                    ? auditors.find((a) => a.id === u.assigned_auditor_id)?.username ||
                      "—"
                    : "—"}
                </td>
                <td>
                  <button
                    onClick={() => handleEdit(u)}
                    className="btn btn-sm"
                    style={{ marginLeft: "5px" }}
                  >
                    تعديل
                  </button>
                  <button
                    onClick={() => handleDelete(u.id)}
                    className="btn btn-sm btn-danger"
                  >
                    حذف
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
